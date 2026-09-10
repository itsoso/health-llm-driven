"""Upload may overlap deployment, without replay or a false release success."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from test_trusted_release_server import SHA, policy, setup_state


def setup_parallel_state(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "validate_loopback", lambda _policy: None)
    return server


def test_upload_can_precede_backend_without_consuming_its_claim(monkeypatch, tmp_path):
    server = setup_parallel_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    assert server.claim_build(policy(), tmp_path) == {"sha": SHA, "state": "CLAIMED"}
    assert server.read_status(SHA, tmp_path)["state"] == "READY"
    assert server.claim_testflight(policy(), tmp_path)["state"] == "CLAIMED"
    assert server.read_status(SHA, tmp_path)["state"] == "READY"
    assert server.run_once(policy(), tmp_path, lambda: None, lambda: None)["state"] == "SUCCEEDED"
    with pytest.raises(server.LaunchError):
        server.claim_build(policy(), tmp_path)


@pytest.mark.parametrize("failure", ["network", "expiry"])
def test_readiness_failure_never_consumes_build_or_backend(monkeypatch, tmp_path, failure):
    server = setup_state(monkeypatch, tmp_path)
    def fail(_policy):
        if failure == "expiry":
            monkeypatch.setattr(server.time, "time", lambda: 200)
        else:
            raise server.LaunchError("readiness failed")
    monkeypatch.setattr(server, "check_readiness", fail)
    with pytest.raises(server.LaunchError):
        server.claim_build(policy(), tmp_path)
    assert not (tmp_path / "build-started.json").exists()
    assert not (tmp_path / "started.json").exists()


def test_lost_build_claim_response_cannot_create_again(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    write = server._write_private
    def fail(path, data):
        write(path, data)
        raise ConnectionError("lost response")
    monkeypatch.setattr(server, "_write_private", fail)
    with pytest.raises(ConnectionError):
        server.claim_build(policy(), tmp_path)
    monkeypatch.setattr(server, "_write_private", write)
    with pytest.raises(server.LaunchError):
        server.claim_build(policy(), tmp_path)


def test_readiness_checks_real_transport_and_loopback_with_bounded_clean_commands(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(server, "validate_loopback", lambda _policy: calls.append("metadata"))
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=f"{SHA}\trefs/heads/main\n")
    monkeypatch.setattr(server.subprocess, "run", run)
    server.check_readiness(policy())
    assert calls[0] == "metadata"
    git, ssh = calls[1:]
    assert "http.version=HTTP/1.1" in git[0]
    assert git[0][-2:] == [server.ORIGIN, "refs/heads/main"]
    assert ssh[0][-2:] == ["health", "/usr/bin/true"]
    for _, kwargs in (git, ssh):
        assert kwargs["timeout"] <= 90
        assert kwargs["check"] is True
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert "EXPO_TOKEN" not in kwargs["env"]


def test_readiness_rejects_remote_main_drift(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "validate_loopback", lambda _policy: None)
    monkeypatch.setattr(server.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="b" * 40 + "\trefs/heads/main\n"))
    with pytest.raises(server.LaunchError):
        server.check_readiness(policy())


def test_build_claim_is_blocked_by_failed_backend(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    (tmp_path / "started.json").write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    (tmp_path / "completed.json").write_text(json.dumps({"sha": SHA, "state": "NEEDS_OPERATOR"}))
    with pytest.raises(server.LaunchError):
        server.claim_build(policy(), tmp_path)
    assert not (tmp_path / "build-started.json").exists()


def test_build_and_upload_can_run_while_backend_holds_its_lock(monkeypatch, tmp_path):
    server = setup_parallel_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    def during_deploy():
        assert server.claim_build(policy(), tmp_path)["state"] == "CLAIMED"
        assert server.claim_testflight(policy(), tmp_path)["state"] == "CLAIMED"
        assert server.read_status(SHA, tmp_path)["state"] == "STARTED"
    assert server.run_once(policy(), tmp_path, lambda: None, during_deploy)["state"] == "SUCCEEDED"


def test_parallel_build_claim_cannot_race_another_build(monkeypatch, tmp_path):
    import fcntl
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    with (tmp_path / "build.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(server.LaunchError):
            server.claim_build(policy(), tmp_path)
    assert not (tmp_path / "build-started.json").exists()


@pytest.mark.parametrize("marker", [None, {}, {"sha": "b" * 40, "state": "STARTED"},
                                  {"sha": SHA, "state": "FINISHED"}])
def test_upload_requires_exact_build_claim(monkeypatch, tmp_path, marker):
    server = setup_state(monkeypatch, tmp_path)
    server.run_once(policy(), tmp_path, lambda: None, lambda: None)
    if marker is not None:
        (tmp_path / "build-started.json").write_text(json.dumps(marker))
        (tmp_path / "build-started.json").chmod(0o600)
    with pytest.raises(server.LaunchError, match="exact build claim"):
        server.claim_testflight(policy(), tmp_path)
    assert not (tmp_path / "native-started.json").exists()


def test_expired_upload_cannot_consume_native_marker(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    server.claim_build(policy(), tmp_path)
    server.run_once(policy(), tmp_path, lambda: None, lambda: None)
    monkeypatch.setattr(server.time, "time", lambda: 7400)
    with pytest.raises(server.LaunchError):
        server.claim_testflight(policy(), tmp_path)
    assert not (tmp_path / "native-started.json").exists()


@pytest.mark.parametrize("preparing", [True, False])
def test_backend_failure_after_upload_preserves_failure_and_both_claims(monkeypatch, tmp_path, preparing):
    server = setup_parallel_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    server.claim_build(policy(), tmp_path)
    server.claim_testflight(policy(), tmp_path)
    before = {name: (tmp_path / name).read_bytes() for name in ("build-started.json", "native-started.json")}
    def fail():
        raise RuntimeError("backend failed after upload")
    with pytest.raises(server.LaunchError):
        server.run_once(policy(), tmp_path, fail if preparing else lambda: None,
                        (lambda: None) if preparing else fail)
    assert server.release_status(SHA, tmp_path) == {
        "sha": SHA, "backend": "PREPARATION_FAILED" if preparing else "NEEDS_OPERATOR", "testflight": "STARTED",
    }
    for claim in (server.claim_build, server.claim_testflight):
        with pytest.raises(server.LaunchError):
            claim(policy(), tmp_path)
    assert before == {name: (tmp_path / name).read_bytes() for name in before}


def test_revoked_identity_blocks_an_already_authenticated_upload_session(monkeypatch, tmp_path):
    server = setup_parallel_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    server.claim_build(policy(), tmp_path)
    server.run_once(policy(), tmp_path, lambda: None, lambda: None)
    def revoked(_policy):
        raise server.LaunchError("authorization revoked")
    monkeypatch.setattr(server, "validate_loopback", revoked)
    with pytest.raises(server.LaunchError, match="revoked"):
        server.claim_testflight(policy(), tmp_path)
    assert not (tmp_path / "native-started.json").exists()
