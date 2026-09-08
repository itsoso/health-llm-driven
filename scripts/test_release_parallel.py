"""Parallel build must not grant an early upload or a second build."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from test_trusted_release_server import SHA, policy, setup_state


def test_build_claim_does_not_consume_backend_or_grant_upload(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    assert server.claim_build(policy(), tmp_path) == {"sha": SHA, "state": "CLAIMED"}
    assert server.read_status(SHA, tmp_path)["state"] == "READY"
    with pytest.raises(server.LaunchError):
        server.claim_testflight(policy(), tmp_path)
    assert server.run_once(policy(), tmp_path, lambda: None, lambda: None)["state"] == "SUCCEEDED"
    assert server.claim_testflight(policy(), tmp_path)["state"] == "CLAIMED"
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


def test_build_claim_can_run_while_backend_holds_its_lock(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "check_readiness", lambda _policy: None)
    def during_deploy():
        assert server.claim_build(policy(), tmp_path)["state"] == "CLAIMED"
        with pytest.raises(server.LaunchError):
            server.claim_testflight(policy(), tmp_path)
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
