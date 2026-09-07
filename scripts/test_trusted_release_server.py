"""One-shot server launcher: no production network or mutation in tests."""

import hashlib
import importlib.util
import io
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).with_name("trusted_release_server.py")
SHA = "a" * 40
HASH = "b" * 64


def load_server():
    assert SCRIPT.exists(), "The forced-command one-shot launcher must exist"
    spec = importlib.util.spec_from_file_location("release_server", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def policy(**changes):
    result = {"sha": SHA, "expires_at": 7300, "executor_sha256": HASH}
    result.update(changes)
    return result


@pytest.mark.parametrize("command", ["", "run ", " run", "run\n", "run a", "run;id", "status /etc/passwd", "bash", "RUN", "run", "status", "claim-testflight", "claim-testflight " + "A" * 40, "run " + SHA + "\n", "run " + SHA + " extra"])
def test_only_exact_commands_are_accepted(command):
    server = load_server()
    with pytest.raises(server.LaunchError):
        server.parse_command(command)


def test_actions_bind_an_exact_expected_sha():
    server = load_server()
    assert server.parse_command("run " + SHA) == ("run", SHA)
    assert server.parse_command("status " + SHA) == ("status", SHA)
    assert server.parse_command("claim-testflight " + SHA) == ("claim-testflight", SHA)


@pytest.mark.parametrize("action", ["run", "status", "claim-testflight"])
def test_rpc_sha_only_compares_with_policy_and_cannot_select_a_release(action):
    server = load_server()
    with pytest.raises(server.LaunchError):
        server.authorize_command(action + " " + "c" * 40, policy())
    assert server.authorize_command(action + " " + SHA, policy()) == action


@pytest.mark.parametrize("changes", [{"sha": "main"}, {"sha": "A" * 40}, {"expires_at": True}, {"expires_at": 100}, {"expires_at": 99}, {"executor_sha256": "bad"}, {"command": "id"}])
def test_policy_rejects_expiry_and_injected_fields(changes):
    server = load_server()
    with pytest.raises(server.LaunchError):
        server.validate_policy(policy(**changes), now=100)


def test_policy_binds_exact_revision_and_executor():
    server = load_server()
    assert server.validate_policy(policy(), now=100) == policy()


@pytest.mark.parametrize("uid,mode,nlink", [(501, 0o600, 1), (0, 0o660, 1), (0, 0o644, 1), (0, 0o600, 2)])
def test_sensitive_file_requires_root_private_single_link(uid, mode, nlink):
    server = load_server()
    metadata = os.stat_result((stat.S_IFREG | mode, 1, 1, nlink, uid, 0, 20, 0, 0, 0))
    with pytest.raises(server.LaunchError):
        server.validate_metadata(metadata, private=True)


def setup_state(monkeypatch, tmp_path):
    server = load_server()
    # Test mutable filesystem/state with this process's UID. Production entry
    # separately enforces root ownership all the way to / and fixed roots.
    monkeypatch.setattr(server, "secure_path", lambda *args, **kwargs: None)
    monkeypatch.setattr(server.time, "time", lambda: 100)
    return server


def test_success_runs_once_and_status_is_minimal(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    calls = []
    outcome = server.run_once(policy(), tmp_path, lambda: calls.append("prepare"), lambda: calls.append("deploy"))
    assert outcome == {"sha": SHA, "state": "SUCCEEDED"}
    assert calls == ["prepare", "deploy"]
    assert server.read_status(SHA, tmp_path) == outcome
    with pytest.raises(server.LaunchError):
        server.run_once(policy(), tmp_path, lambda: calls.append("again"), lambda: None)
    assert calls == ["prepare", "deploy"]


def test_failed_deploy_consumes_authorization_without_cleanup_or_retry(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    evidence = tmp_path / "deploy-lease-evidence"
    def fail():
        evidence.write_text("retained")
        raise RuntimeError("secret health payload")
    with pytest.raises(server.LaunchError) as error:
        server.run_once(policy(), tmp_path, lambda: None, fail)
    assert "secret" not in str(error.value)
    assert server.read_status(SHA, tmp_path) == {"sha": SHA, "state": "NEEDS_OPERATOR"}
    assert evidence.read_text() == "retained"
    with pytest.raises(server.LaunchError):
        server.run_once(policy(), tmp_path, lambda: None, lambda: None)


def test_interruption_keeps_started_marker_and_never_retries(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    def interrupt():
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        server.run_once(policy(), tmp_path, lambda: None, interrupt)
    assert server.read_status(SHA, tmp_path) == {"sha": SHA, "state": "STARTED"}
    with pytest.raises(server.LaunchError):
        server.run_once(policy(), tmp_path, lambda: None, lambda: None)


def test_concurrent_invocation_is_rejected_while_first_still_active(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    def overlap():
        with pytest.raises(server.LaunchError, match="active"):
            server.run_once(policy(), tmp_path, lambda: None, lambda: None)
    assert server.run_once(policy(), tmp_path, lambda: None, overlap)["state"] == "SUCCEEDED"


def test_preparation_failure_is_not_retryable(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    calls = []
    def fail():
        raise OSError("network unavailable")
    with pytest.raises(server.LaunchError):
        server.run_once(policy(), tmp_path, fail, lambda: calls.append("deploy"))
    assert calls == []
    assert server.read_status(SHA, tmp_path)["state"] == "NEEDS_OPERATOR"


def test_clean_environment_does_not_forward_caller_injection(monkeypatch, tmp_path):
    server = load_server()
    monkeypatch.setenv("BASH_ENV", "/tmp/evil")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("PYTHONPATH", "/tmp/evil")
    env = server.clean_environment(tmp_path)
    assert "BASH_ENV" not in env
    assert "PYTHONPATH" not in env
    assert "GIT_CONFIG_COUNT" not in env
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"


def test_source_preparation_uses_fixed_public_origin_and_exact_sha(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    calls = []
    def execute(args, cwd, env, log):
        calls.append(args)
        if "clone" in args:
            source = tmp_path / "source"
            (source / "scripts").mkdir(parents=True)
            (source / "scripts/trusted_release_server.py").write_bytes(b"audited")
            (source / "scripts/trusted_release_gate.py").write_text("pass")
        return ""
    monkeypatch.setattr(server, "execute", execute)
    server.prepare_source(policy(executor_sha256=hashlib.sha256(b"audited").hexdigest()), tmp_path)
    assert any("https://github.com/itsoso/health-llm-driven.git" in args for args in calls)
    assert any(args[-3:] == ["-B", "main", SHA] for args in calls)
    assert any("-I" in args and args[-4:] == ["--sha", SHA, "--workflow-sha", SHA] for args in calls)


def test_source_executor_hash_mismatch_prevents_running_repo_gate(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    calls = []
    def execute(args, cwd, env, log):
        calls.append(args)
        if "clone" in args:
            source = tmp_path / "source/scripts"
            source.mkdir(parents=True)
            (source / "trusted_release_server.py").write_bytes(b"wrong")
        return ""
    monkeypatch.setattr(server, "execute", execute)
    with pytest.raises(server.LaunchError):
        server.prepare_source(policy(), tmp_path)
    assert not any("-I" in args for args in calls)


@pytest.mark.parametrize("uid,gid,mode", [(501, 100, 0o640), (0, 99, 0o640), (0, 100, 0o644), (0, 100, 0o660), (0, 100, 0o600)])
def test_production_env_uses_exact_existing_service_group_contract(uid, gid, mode):
    server = load_server()
    metadata = os.stat_result((stat.S_IFREG | mode, 1, 1, 1, uid, gid, 20, 0, 0, 0))
    with pytest.raises(server.LaunchError):
        server.validate_production_env_metadata(metadata, 100)


def test_production_env_accepts_root_service_group_0640_without_chmod():
    server = load_server()
    metadata = os.stat_result((stat.S_IFREG | 0o640, 1, 1, 1, 0, 100, 20, 0, 0, 0))
    server.validate_production_env_metadata(metadata, 100)


def test_loopback_rejects_added_shell_directives_or_broader_authorization(monkeypatch):
    server = load_server()
    monkeypatch.setattr(server, "secure_path", lambda *args, **kwargs: None)
    values = {
        "loopback.conf": server.loopback_config().encode(),
        "loopback.pub": b"ssh-ed25519 AAAA",
        "authorized_keys": b'from="127.0.0.1",restrict,expiry-time="19700101000320Z" ssh-ed25519 AAAA',
    }
    monkeypatch.setattr(server, "_read_private", lambda path: values[path.name])
    server.validate_loopback(policy(expires_at=200))
    values["authorized_keys"] += b"\nssh-ed25519 AAAA"
    with pytest.raises(server.LaunchError):
        server.validate_loopback(policy(expires_at=200))
    values["authorized_keys"] = values["authorized_keys"].splitlines()[0]
    values["loopback.conf"] += b"  LocalCommand id\n"
    with pytest.raises(server.LaunchError):
        server.validate_loopback(policy(expires_at=200))


def test_deploy_uses_only_fixed_command_and_private_authoritative_env(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server.time, "time", lambda: 100)
    monkeypatch.setattr(server, "validate_loopback", lambda policy: None)
    monkeypatch.setattr(server, "read_production_env", lambda: "EXAMPLE_SETTING=fixture\nDEPLOY_SERVER=old\nDEPLOY_PATH=/old\n")
    calls = []
    monkeypatch.setattr(server, "execute", lambda args, cwd, env, log: calls.append((args, env)))
    server.deploy(policy(), tmp_path)
    assert calls[-1][0] == ["/bin/bash", str(tmp_path / "source/deploy.sh"), "-b"]
    assert calls[-1][1]["DEPLOY_SOURCE_SHA"] == SHA
    candidate = (tmp_path / "deployment.env").read_text()
    assert candidate == "EXAMPLE_SETTING=fixture\nDEPLOY_SERVER=health\nDEPLOY_PATH=/opt/health-app\n"
    assert stat.S_IMODE((tmp_path / "deployment.env").stat().st_mode) == 0o600
    assert (tmp_path / "bin/ssh").read_text() == '#!/bin/sh\nexec /usr/bin/ssh -F /etc/reva-release/loopback.conf "$@"\n'


def test_expired_policy_blocks_deploy_even_after_slow_preparation(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server.time, "time", lambda: 7301)
    with pytest.raises(server.LaunchError):
        server.deploy(policy(), tmp_path)
    assert not (tmp_path / "bin").exists()


def test_native_claim_is_durable_and_cannot_be_reused(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    server.run_once(policy(), tmp_path, lambda: None, lambda: None)
    assert server.release_status(SHA, tmp_path) == {"sha": SHA, "backend": "SUCCEEDED", "testflight": "UNCLAIMED"}
    assert server.claim_testflight(policy(), tmp_path) == {"sha": SHA, "state": "CLAIMED"}
    assert server.release_status(SHA, tmp_path) == {"sha": SHA, "backend": "SUCCEEDED", "testflight": "STARTED"}
    assert stat.S_IMODE((tmp_path / "native-started.json").stat().st_mode) == 0o600
    with pytest.raises(server.LaunchError):
        server.claim_testflight(policy(), tmp_path)


@pytest.mark.parametrize("state", ["READY", "STARTED", "NEEDS_OPERATOR"])
def test_native_claim_requires_confirmed_backend_success(monkeypatch, tmp_path, state):
    server = setup_state(monkeypatch, tmp_path)
    if state != "READY":
        def fail():
            if state == "STARTED":
                raise KeyboardInterrupt()
            raise RuntimeError("failure")
        with pytest.raises((server.LaunchError, KeyboardInterrupt)):
            server.run_once(policy(), tmp_path, lambda: None, fail)
    with pytest.raises(server.LaunchError):
        server.claim_testflight(policy(), tmp_path)
    assert not (tmp_path / "native-started.json").exists()


def test_concurrent_native_claim_is_blocked_before_marker(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    import fcntl
    lock = tmp_path.parent / "launcher.lock"
    with lock.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(server.LaunchError, match="active"):
            server.claim_testflight(policy(), tmp_path)
    assert not (tmp_path / "native-started.json").exists()


@pytest.mark.parametrize("action", ["run", "status", "claim-testflight"])
def test_main_rejects_sha_mismatch_before_any_state_or_source_mutation(monkeypatch, tmp_path, action):
    server = load_server()
    monkeypatch.setattr(server, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1), argv=["fixed"], stderr=io.StringIO()))
    monkeypatch.setattr(server.os, "geteuid", lambda: 0)
    monkeypatch.setattr(server.os, "umask", lambda _mode: None)
    monkeypatch.setattr(server.time, "time", lambda: 100)
    monkeypatch.setattr(server, "STATE", tmp_path / "not-created")
    monkeypatch.setattr(server, "_read_private", lambda _path: json.dumps(policy()).encode())
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", action + " " + "c" * 40)
    assert server.main() == 1
    assert "caller SHA" in server.sys.stderr.getvalue()
    assert not server.STATE.exists()


def test_lost_native_claim_response_never_grants_a_second_build(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    server.run_once(policy(), tmp_path, lambda: None, lambda: None)
    write = server._write_private
    def interrupted(path, data):
        write(path, data)
        raise ConnectionError("response lost after durable claim")
    monkeypatch.setattr(server, "_write_private", interrupted)
    with pytest.raises(ConnectionError):
        server.claim_testflight(policy(), tmp_path)
    monkeypatch.setattr(server, "_write_private", write)
    assert server.release_status(SHA, tmp_path)["testflight"] == "STARTED"
    with pytest.raises(server.LaunchError):
        server.claim_testflight(policy(), tmp_path)


@pytest.mark.parametrize("remaining", [7199, 7200, 7201])
def test_run_requires_full_deployment_and_recovery_window_before_marker(monkeypatch, tmp_path, remaining):
    server = setup_state(monkeypatch, tmp_path)
    calls = []
    authorized = policy(expires_at=100 + remaining)
    if remaining < 7200:
        with pytest.raises(server.LaunchError, match="lifetime"):
            server.run_once(authorized, tmp_path, lambda: calls.append("prepare"), lambda: calls.append("deploy"))
        assert calls == []
        assert not (tmp_path / "started.json").exists()
    else:
        assert server.run_once(authorized, tmp_path, lambda: calls.append("prepare"), lambda: calls.append("deploy"))["state"] == "SUCCEEDED"
        assert calls == ["prepare", "deploy"]


def test_preparation_cannot_spend_the_reserved_deployment_window(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    calls = []
    def prepare():
        calls.append("prepare")
        monkeypatch.setattr(server.time, "time", lambda: 101)
    with pytest.raises(server.LaunchError):
        server.run_once(policy(), tmp_path, prepare, lambda: calls.append("deploy"))
    assert calls == ["prepare"]
    assert server.read_status(SHA, tmp_path)["state"] == "NEEDS_OPERATOR"


def test_last_ci_check_cannot_spend_the_reserved_deployment_window(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "validate_loopback", lambda policy: None)
    monkeypatch.setattr(server, "read_production_env", lambda: "EXAMPLE_SETTING=fixture\n")
    calls = []
    def slow_ci(args, cwd, env, log):
        calls.append(args)
        monkeypatch.setattr(server.time, "time", lambda: 101)
    monkeypatch.setattr(server, "execute", slow_ci)
    with pytest.raises(server.LaunchError, match="lifetime"):
        server.deploy(policy(), tmp_path)
    assert len(calls) == 1
    assert calls[0][0] == "/usr/bin/python3.12"
    assert not any("/bin/bash" in command for command in calls)


def test_workspace_parent_directory_is_durable_before_preparation(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    events = []
    parent_identity = (tmp_path.parent.stat().st_dev, tmp_path.parent.stat().st_ino)
    real_fsync = server.os.fsync
    def observe(fd):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == parent_identity:
            events.append("parent-fsync")
        return real_fsync(fd)
    monkeypatch.setattr(server.os, "fsync", observe)
    server.run_once(policy(), tmp_path, lambda: events.append("prepare"), lambda: events.append("deploy"))
    assert events[:3] == ["parent-fsync", "prepare", "deploy"]


def test_workspace_parent_fsync_failure_preserves_marker_and_blocks_all_work(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    calls = []
    parent_identity = (tmp_path.parent.stat().st_dev, tmp_path.parent.stat().st_ino)
    real_fsync = server.os.fsync
    def fail_parent(fd):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == parent_identity:
            raise OSError("parent durability unavailable")
        return real_fsync(fd)
    monkeypatch.setattr(server.os, "fsync", fail_parent)
    with pytest.raises((server.LaunchError, OSError)):
        server.run_once(policy(), tmp_path, lambda: calls.append("prepare"), lambda: calls.append("deploy"))
    assert calls == []
    assert (tmp_path / "started.json").exists()
    with pytest.raises(server.LaunchError):
        server.run_once(policy(), tmp_path, lambda: calls.append("prepare"), lambda: calls.append("deploy"))
    assert calls == []
