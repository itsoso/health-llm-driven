"""Finalization is a narrow operator path; ordinary launchers fail closed."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name + "_integration", Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def history(tmp_path, monkeypatch):
    server = load("trusted_release_server")
    state = tmp_path / "state"
    audit = state / "frontend-rebuilds" / ("c" * 32)
    audit.mkdir(parents=True, mode=0o700)
    audit.parent.chmod(0o700)
    monkeypatch.setattr(server, "STATE", state)
    monkeypatch.setattr(server, "secure_path", lambda *a, **k: None)
    calls = []
    proof = SimpleNamespace(
        original_evidence=lambda *a, **k: calls.append("original"),
        history_evidence=lambda *a, **k: calls.append("terminal"),
    )
    monkeypatch.setattr(server, "_load_frontend_finalizer", lambda: proof)
    return server, state, audit, proof, calls


def test_selected_finalization_must_validate_original_profile(history):
    server, state, audit, proof, calls = history
    server.assert_frontend_rebuild_history(state, pending_finalization_operation=audit.name)
    assert calls == ["original"]
    proof.original_evidence = lambda *a, **k: (_ for _ in ()).throw(ValueError("invalid original"))
    with pytest.raises(ValueError, match="invalid original"):
        server.assert_frontend_rebuild_history(state, pending_finalization_operation=audit.name)


def test_selected_exception_does_not_skip_other_unfinished_operations(history):
    server, state, audit, _, calls = history
    (audit.parent / ("d" * 32)).mkdir(mode=0o700)
    with pytest.raises(server.LaunchError, match="unfinished"):
        server.assert_frontend_rebuild_history(state, pending_finalization_operation=audit.name)


def test_absent_selected_operation_blocks(history):
    server, state, audit, _, _ = history
    audit.rmdir()
    with pytest.raises(server.LaunchError, match="missing"):
        server.assert_frontend_rebuild_history(state, pending_finalization_operation=audit.name)


def test_finalized_history_uses_independent_terminal_proof(history):
    server, state, audit, _, calls = history
    closure = state / "frontend-finalizations" / audit.name
    closure.mkdir(parents=True, mode=0o700)
    closure.parent.chmod(0o700)
    server.assert_frontend_rebuild_history(state)
    assert calls == ["terminal"]


def test_ordinary_history_never_treats_partial_finalization_as_success(history):
    server, state, audit, proof, _ = history
    closure = state / "frontend-finalizations" / audit.name
    closure.mkdir(parents=True, mode=0o700)
    closure.parent.chmod(0o700)
    (closure / "intent.json").write_text("{}")
    proof.history_evidence = lambda *a, **k: (_ for _ in ()).throw(ValueError("partial"))
    with pytest.raises(ValueError, match="partial"):
        server.assert_frontend_rebuild_history(state)


def test_orphan_finalization_blocks_even_without_frontend_audit(history):
    server, state, _, _, _ = history
    closure = state / "frontend-finalizations" / ("d" * 32)
    closure.mkdir(parents=True, mode=0o700)
    closure.parent.chmod(0o700)
    with pytest.raises(server.LaunchError, match="orphan"):
        server.assert_frontend_rebuild_history(state)


@pytest.mark.parametrize("tamper", [False, True])
def test_finalizer_helper_bytes_must_match_exact_canonical_blob(tmp_path, monkeypatch, tamper):
    server = load("trusted_release_server")
    state = tmp_path / "state"
    source = state / "bootstrap" / ("a" * 40) / "source"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "frontend_verified_finalization.py"
    script.write_text("VALUE = 42\n")
    monkeypatch.setattr(server, "STATE", state)
    monkeypatch.setattr(server, "__file__", str(scripts / "trusted_release_server.py"))
    monkeypatch.setattr(server, "secure_path", lambda *a, **k: None)
    def blob(args, **kwargs):
        assert args[-1] == "a" * 40 + ":scripts/frontend_verified_finalization.py"
        assert kwargs["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert kwargs["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"
        return SimpleNamespace(stdout=b"VALUE = 43\n" if tamper else script.read_bytes())
    monkeypatch.setattr(server.subprocess, "run", blob)
    if tamper:
        with pytest.raises(server.LaunchError, match="differs"):
            server._load_frontend_finalizer()
    else:
        assert server._load_frontend_finalizer().VALUE == 42
        assert not (scripts / "__pycache__").exists()


def test_operator_refuses_build_lock_appearing_after_absence(tmp_path, monkeypatch):
    frontend = load("trusted_frontend_rebuild")
    monkeypatch.setattr(frontend, "STATE", tmp_path)
    production = "b" * 40
    build = tmp_path / production / "build.lock"
    build.parent.mkdir()
    def inspect(*args, check_locks, **kwargs):
        check_locks()
        build.write_text("")
        check_locks()
    module = SimpleNamespace(inspect_finalization=inspect)
    server = SimpleNamespace(_load_frontend_finalizer=lambda: module)
    helper = SimpleNamespace(_assert_lock=lambda *a: None)
    bootstrap = SimpleNamespace(_acquire_existing_build_lock=lambda *a: None)
    args = SimpleNamespace(publisher_sha="a" * 40, production_sha=production,
                           operation_id="c" * 32, evidence_sha256=None)
    with pytest.raises(frontend.RebuildError, match="lock appeared"):
        frontend.finalize_verified(args, Path("/unused"), helper, bootstrap, server, None, 1)
