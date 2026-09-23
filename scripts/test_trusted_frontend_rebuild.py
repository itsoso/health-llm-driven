"""Offline tests: never connect to production or execute package managers."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import uuid

import pytest


def load():
    path = Path(__file__).with_name("trusted_frontend_rebuild.py")
    spec = importlib.util.spec_from_file_location("frontend_rebuild_tested", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_binding_refuses_drift_and_unproven_backend():
    m = load()
    args = ("a" * 40, "b" * 40, "c" * 40, "c" * 40)
    m.validate_binding(*args, {"sha": "b" * 40, "state": "SUCCEEDED"})
    for live, tree, receipt in [
        ("d" * 40, "c" * 40, {"sha": "b" * 40, "state": "SUCCEEDED"}),
        ("b" * 40, "d" * 40, {"sha": "b" * 40, "state": "SUCCEEDED"}),
        ("b" * 40, "c" * 40, {"sha": "b" * 40, "state": "STARTED"}),
        ("b" * 40, "c" * 40, {"sha": "a" * 40, "state": "SUCCEEDED"}),
    ]:
        with pytest.raises(m.RebuildError):
            m.validate_binding("a" * 40, "b" * 40, "c" * 40, tree, receipt, live_sha=live)


def test_build_is_unprivileged_and_cannot_read_production_or_release_credentials():
    m = load()
    command = m.build_command("a" * 32, Path("/var/lib/reva-frontend-builds") / ("a" * 32))
    joined = " ".join(command)
    for required in ["DynamicUser=yes", "ProtectSystem=strict", "ProtectHome=yes",
                     "ProtectProc=invisible", "NoNewPrivileges=yes", "KillMode=control-group",
                     "WorkingDirectory=/tmp/reva-frontend", "BindPaths="]:
        assert required in joined
    denied = next(arg.split("=", 2)[2].split() for arg in command if arg.startswith("--property=InaccessiblePaths="))
    for required in ("/opt", "/var/lib", "/var/cache", "/var/log", "/var/backups",
                     "/srv", "/data", "/mnt", "/media", "/etc/reva-release", "/etc/health-app"):
        assert "-" + required in denied
    assert "npm ci --ignore-scripts" in joined
    assert "npm run build" in joined
    assert "--collect" not in command  # keep unit evidence until separately verified


def test_deploy_entry_precedes_env_and_never_reinterprets_normal_frontend_mode():
    script = (Path(__file__).resolve().parents[1] / "deploy.sh").read_text()
    assert script.index('--rebuild-deployed-frontend') < script.index('ENV_FILE=')
    assert '"$SCRIPT_DIR/scripts/trusted_frontend_rebuild.py" "$@"' in script
    assert 'if ! verify_deployed_revision; then' in script


def test_success_receipt_is_frontend_specific_and_binds_both_revisions():
    m = load()
    value = m.receipt("a" * 40, "b" * 40, "c" * 32, "d" * 40, "FRONTEND_SUCCEEDED", "e" * 64)
    assert value == {"kind": "frontend-rebuild", "publisher_sha": "a" * 40,
                     "production_sha": "b" * 40, "operation_id": "c" * 32,
                     "frontend_tree": "d" * 40, "state": "FRONTEND_SUCCEEDED",
                     "artifact_digest": "e" * 64}
    assert "sha" not in value


def test_artifact_manifest_rejects_links_outside_bundle(tmp_path):
    m = load()
    (tmp_path / "safe").write_text("payload")
    first = m.artifact_digest(tmp_path)
    (tmp_path / "safe").write_text("changed")
    assert m.artifact_digest(tmp_path) != first
    (tmp_path / "escape").symlink_to("/etc/passwd")
    with pytest.raises(m.RebuildError):
        m.artifact_digest(tmp_path)


def test_build_env_file_rejects_unknown_keys_and_expansion():
    m = load()
    assert m.public_build_env("BACKEND_URL=http://127.0.0.1:8000\n") == {"BACKEND_URL": "http://127.0.0.1:8000"}
    for value in ["SECRET_KEY=secret", "BACKEND_URL=$(id)", "BACKEND_URL=https://user:pass@example.com", "NODE_OPTIONS=--require=evil", "BACKEND_URL=http://127.0.0.1:8000\nBACKEND_URL=http://localhost:8000"]:
        with pytest.raises(m.RebuildError):
            m.public_build_env(value)


def test_unfinished_frontend_audit_blocks_later_backend_operations(tmp_path, monkeypatch):
    path = Path(__file__).with_name("trusted_release_server.py")
    spec = importlib.util.spec_from_file_location("frontend_audit_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    monkeypatch.setattr(server, "secure_path", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_read_private", lambda p: p.read_bytes())
    root = tmp_path / "frontend-rebuilds"
    root.mkdir(mode=0o700)
    op = root / ("c" * 32)
    op.mkdir(mode=0o700)
    m = load()
    intent = m.receipt("a" * 40, "b" * 40, op.name, "d" * 40, "FRONTEND_STARTED", None)
    (op / "intent.json").write_text(json.dumps(intent))
    with pytest.raises(server.LaunchError):
        server.assert_frontend_rebuild_history(tmp_path)
    for name, state in [("install-started.json", "FRONTEND_INSTALLING"), ("verified.json", "FRONTEND_VERIFIED"), ("completed.json", "FRONTEND_SUCCEEDED")]:
        (op / name).write_text(json.dumps(m.receipt("a" * 40, "b" * 40, op.name, "d" * 40, state, "e" * 64)))
    (op / "before.json").write_text(json.dumps({"publisher_sha": "a" * 40, "production_sha": "b" * 40, "operation_id": op.name, "frontend_tree": "d" * 40}))
    (op / "build.log").write_text("build complete")
    (op / "previous-next").mkdir()
    (op / "previous-node-modules").mkdir()
    server.assert_frontend_rebuild_history(tmp_path)
    (op / "failed.json").write_text("{}")
    with pytest.raises(server.LaunchError):
        server.assert_frontend_rebuild_history(tmp_path)


@pytest.fixture
def execution(tmp_path, monkeypatch):
    m = load()
    for name, path in [("STATE", tmp_path / "state"), ("PRODUCTION", tmp_path / "production"),
                       ("BUILDS", tmp_path / "builds"), ("LEASE", tmp_path / "lease")]:
        monkeypatch.setattr(m, name, path)
    m.STATE.mkdir()
    m.PRODUCTION.mkdir()
    (m.PRODUCTION / "frontend").mkdir()
    for name in (".next", "node_modules"):
        path = m.PRODUCTION / "frontend" / name
        path.mkdir()
        (path / "payload").write_text("old")
    events = []
    def prepare(source, stage, environment):
        events.append("build-inputs")
        for name in (".next", "node_modules"):
            path = stage / "frontend" / name
            path.mkdir(parents=True)
            (path / "payload").write_text("new")
    monkeypatch.setattr(m, "copy_build_inputs", prepare)
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **kw: events.append("build"))
    monkeypatch.setattr(m, "freeze_artifacts", lambda *a: "e" * 64)
    monkeypatch.setattr(m, "assert_unchanged", lambda *a: events.append("unchanged"))
    monkeypatch.setattr(m, "run", lambda args, **kw: events.append(args[1]))
    monkeypatch.setattr(m, "assert_frontend_stopped", lambda: events.append("stopped"))
    monkeypatch.setattr(m, "verify_pages", lambda: events.append("readback"))
    def write(path, data):
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(0o600)
    server = SimpleNamespace(_write_private=write, _sync_directory=lambda p: None, secure_path=lambda *a, **kw: None)
    helper = SimpleNamespace(_lease_identity=lambda *a: ((1, 2), (1, 3)))
    plan = {"publisher_sha": "a" * 40, "production_sha": "b" * 40,
            "operation_id": "c" * 32, "frontend_tree": "d" * 40, "public_build_env": {}}
    return m, plan, helper, server, events


def test_execution_preserves_old_artifacts_and_only_stops_frontend(execution):
    m, plan, helper, server, events = execution
    result = m.execute(plan, Path("/unused"), helper, None, server)
    assert result["state"] == "FRONTEND_SUCCEEDED"
    assert events == ["build-inputs", "build", "unchanged", "stop", "stopped", "restart", "readback", "unchanged"]
    audit = m.STATE / "frontend-rebuilds" / plan["operation_id"]
    assert (audit / "previous-next/payload").read_text() == "old"
    assert (audit / "previous-node-modules/payload").read_text() == "old"
    assert (m.PRODUCTION / "frontend/.next/payload").read_text() == "new"
    assert not m.LEASE.exists()
    assert not (m.STATE / plan["publisher_sha"]).exists()
    with pytest.raises(FileExistsError):
        m.execute(plan, Path("/unused"), helper, None, server)


@pytest.mark.parametrize("failure", ["assert_unchanged", "assert_frontend_stopped", "verify_pages"])
def test_failed_or_unverified_execution_retains_lease_and_never_claims_success(execution, monkeypatch, failure):
    m, plan, helper, server, events = execution
    def fail(*a):
        raise m.RebuildError("test failure")
    monkeypatch.setattr(m, failure, fail)
    with pytest.raises(m.RebuildError):
        m.execute(plan, Path("/unused"), helper, None, server)
    audit = m.STATE / "frontend-rebuilds" / plan["operation_id"]
    assert m.LEASE.is_dir()
    assert (audit / "failed.json").is_file()
    assert not (audit / "completed.json").exists()
    if failure == "assert_unchanged":
        assert "stop" not in events
    if failure == "assert_frontend_stopped":
        assert (m.PRODUCTION / "frontend/.next/payload").read_text() == "old"


@pytest.mark.skipif(os.environ.get("REVA_TEST_FRONTEND_SANDBOX") != "1", reason="requires isolated Linux systemd runner")
def test_native_frontend_sandbox_private_mounts_and_dynamic_uid(monkeypatch):
    assert os.geteuid() == 0 and Path("/run/systemd/system").is_dir()
    m = load()
    root = Path(tempfile.mkdtemp(prefix="reva-frontend-sandbox-", dir="/var/lib"))
    root.chmod(0o755)
    operation = uuid.uuid4().hex
    stage = root / operation
    stage.mkdir(mode=0o700)
    monkeypatch.setattr(m, "BUILDS", root)
    for name in ("frontend", "home", "cache"):
        (stage / name).mkdir(mode=0o777)
        (stage / name).chmod(0o777)
    (stage / "frontend/input").write_text("public source")
    (stage / "frontend/input").chmod(0o644)
    command = m.build_command(operation, stage)
    # Exercise the actual production deny list, never replace it with a test-only path.
    denied = next(arg.split("=", 2)[2].split() for arg in command if arg.startswith("--property=InaccessiblePaths="))
    created_roots, canaries = [], []
    for entry in denied:
        directory = Path(entry.removeprefix("-"))
        assert directory.is_absolute() and not directory.is_symlink()
        if not directory.exists():
            directory.mkdir(mode=0o755)
            created_roots.append(directory)
        canary = Path(tempfile.mkdtemp(prefix="reva-synthetic-health-", dir=directory))
        canary.chmod(0o755)
        (canary / "record").write_text("synthetic test data only")
        (canary / "record").chmod(0o644)
        canaries.append(canary)
    # Real deployments keep world-readable uploads below these external roots.
    assert "-/opt" in denied and "-/var/lib" in denied
    negative_checks = "".join(f"test ! -r {path}/record\n" for path in canaries)
    command[-1] = (f"test -r /tmp/reva-frontend/input\ntest ! -r {stage}/frontend/input\n"
                   + negative_checks + "test -z \"${REVA_SYNTHETIC_SECRET:-}\"\n"
                   "test \"$HOME\" = /tmp/reva-home\nid -u > uid\ntouch /tmp/reva-home/proof /tmp/reva-cache/proof")
    completed = False
    try:
        result = subprocess.run(command, env={**m.ENV, "REVA_SYNTHETIC_SECRET": "must-not-propagate"},
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr
        uid = int((stage / "frontend/uid").read_text())
        assert uid not in (0, 65534)
        assert (stage / "home/proof").is_file() and (stage / "cache/proof").is_file()
        completed = True
    finally:
        # Isolated CI only. Never remove existing root contents; keep unknown units/evidence.
        if completed:
            for canary in canaries:
                (canary / "record").unlink()
                canary.rmdir()
            for directory in reversed(created_roots):
                directory.rmdir()
            shutil.rmtree(root)
