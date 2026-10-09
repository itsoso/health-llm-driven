"""Bootstrap tests run only in temporary local fixtures, never production."""

import base64
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).with_name("bootstrap_trusted_release.py")
SHA = "a" * 40
PUBLIC = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))).decode()
LOOPBACK = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32, 64))).decode()
HOST = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(64, 96))).decode()


def load_bootstrap():
    assert SCRIPT.exists(), "The reviewed one-shot bootstrap must exist"
    spec = importlib.util.spec_from_file_location("release_bootstrap", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("sha,expiry,public", [
    ("main", 200, PUBLIC), (SHA, 100, PUBLIC), (SHA, -1, PUBLIC),
    (SHA, None, PUBLIC), (SHA, 0.0, PUBLIC),
    (SHA, True, PUBLIC), (SHA, 200, PUBLIC + " comment"),
    (SHA, 200, 'command="id" ' + PUBLIC), (SHA, 200, PUBLIC + "\n"),
    (SHA, 200, "ssh-ed25519 AAAAFixture"),
    (SHA, 200, "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x1f" + bytes(range(31))).decode()),
    (SHA, 200, "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(33))).decode()),
])
def test_install_inputs_reject_malformed_or_expired_authorization(sha, expiry, public):
    bootstrap = load_bootstrap()
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.validate_install(sha, expiry, public, now=100)


def test_valid_install_inputs_are_exact_not_normalized():
    bootstrap = load_bootstrap()
    bootstrap.validate_install(SHA, 100 + 28800, PUBLIC, now=100)


@pytest.mark.parametrize("expiry", [0, 100 + 86400 * 90])
def test_install_accepts_persistent_or_explicit_future_deadline(expiry):
    load_bootstrap().validate_install(SHA, expiry, PUBLIC, now=100)


def test_persistent_authorization_keeps_forced_command_and_loopback_isolation():
    cloud, loopback = load_bootstrap().key_lines(0, PUBLIC, LOOPBACK)
    assert cloud == 'command="/usr/bin/python3 -I /usr/local/lib/reva-release/trusted_release_server.py",restrict ' + PUBLIC
    assert loopback == 'from="127.0.0.1",restrict ' + LOOPBACK


def test_persistent_install_is_revocable_without_expiration(monkeypatch, tmp_path):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 0, PUBLIC)
    assert json.loads((bootstrap.CONFIG / "authorized-release.json").read_text())["expires_at"] == 0
    assert "expiry-time" not in bootstrap.AUTHORIZED.read_text()
    assert bootstrap.revoke(SHA)["state"] == "REVOKED"
    assert bootstrap.AUTHORIZED.read_text() == "ssh-ed25519 AAAAExisting unrelated\n"


@pytest.mark.parametrize("action", ["install", "rotate"])
def test_cli_defaults_to_persistent_authorization(monkeypatch, capsys, action):
    bootstrap = load_bootstrap()
    argv = [str(SCRIPT), action, "--sha", SHA, "--cloud-public-key", PUBLIC]
    if action == "rotate":
        argv += ["--retire-sha", "b" * 40]
    monkeypatch.setattr(bootstrap.sys, "argv", argv)
    monkeypatch.setattr(bootstrap.sys, "flags", SimpleNamespace(isolated=1))
    monkeypatch.setattr(bootstrap.os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap.os, "umask", lambda mask: 0o077)
    calls = []
    def install(sha, expiry, public):
        calls.append((sha, expiry, public))
        return {"state": "INSTALLED"}
    monkeypatch.setattr(bootstrap, "install", install)
    monkeypatch.setattr(bootstrap, "rotate", lambda old, sha, expiry, public, **kwargs: install(sha, expiry, public))
    assert bootstrap.main() == 0
    assert calls == [(SHA, 0, PUBLIC)]
    assert PUBLIC not in capsys.readouterr().out


def test_workspace_evidence_rejects_conflicting_closure_profiles(monkeypatch, tmp_path):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    for name in ("unchanged-release-closures", "contained-release-closures"):
        (bootstrap.STATE / name / SHA).mkdir(parents=True)
    with pytest.raises(bootstrap.BootstrapError, match="conflicting"):
        bootstrap._workspace_evidence(SHA)


def test_workspace_evidence_uses_distinct_lost_receipt_acknowledgment(monkeypatch, tmp_path):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    old = "a" * 40
    closure = bootstrap.STATE / "unchanged-release-closures" / old
    closure.mkdir(parents=True)
    acknowledgment = bootstrap.STATE / "lost-closure-receipt-acknowledgments" / old
    acknowledgment.mkdir(parents=True)
    source = tmp_path / "canonical"
    source.mkdir()
    for name in ("contained_release_retirement.py", "lost_closure_receipt_acknowledgment.py"):
        (source / name).write_text("# fixture\n")
    bootstrap.__file__ = str(source / "bootstrap_trusted_release.py")
    monkeypatch.setattr(bootstrap, "secure", lambda *args, **kwargs: None)
    imported = SimpleNamespace(
        acknowledged_evidence=lambda b, sha, receipt, **kwargs: {
            "state": "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT",
            "sha": sha,
            "receipt": receipt,
        })
    monkeypatch.setattr(bootstrap.importlib.util, "module_from_spec", lambda spec: imported)
    monkeypatch.setattr(bootstrap.importlib.util, "spec_from_file_location", lambda *args: SimpleNamespace(
        loader=SimpleNamespace(exec_module=lambda module: None)))
    monkeypatch.setattr(bootstrap, "sys", SimpleNamespace(modules={bootstrap.__name__: bootstrap}, dont_write_bytecode=False))
    evidence = bootstrap._workspace_evidence(old, recovery_receipt="c" * 64)
    assert evidence["state"] == "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT"


def test_key_lines_are_fixed_expiring_and_loopback_cannot_be_remote(monkeypatch):
    bootstrap = load_bootstrap()
    monkeypatch.setattr(bootstrap, "expiry_time", lambda _expiry: "19700101000320", raising=False)
    cloud, loopback = bootstrap.key_lines(200, PUBLIC, "ssh-ed25519 AAAA")
    assert cloud == 'command="/usr/bin/python3 -I /usr/local/lib/reva-release/trusted_release_server.py",restrict,expiry-time="19700101000320" ' + PUBLIC
    assert loopback == 'from="127.0.0.1",restrict,expiry-time="19700101000320" ssh-ed25519 AAAA'


@pytest.mark.parametrize("offset,expected", [(0, "19700101000320"), (8, "19700101080320")])
def test_expiry_uses_system_local_time_and_discards_caller_tz(monkeypatch, offset, expected):
    bootstrap = load_bootstrap()
    real_tzset = bootstrap.time.tzset
    clock = bootstrap.datetime.datetime
    system_zone = bootstrap.datetime.timezone(bootstrap.datetime.timedelta(hours=offset))
    class SystemDateTime:
        @staticmethod
        def fromtimestamp(value):
            return clock.fromtimestamp(value, system_zone).replace(tzinfo=None)
    def simulated_system_timezone():
        assert "TZ" not in os.environ
    monkeypatch.setattr(bootstrap, "datetime", SimpleNamespace(datetime=SystemDateTime))
    monkeypatch.setattr(bootstrap.time, "tzset", simulated_system_timezone)
    monkeypatch.setattr(bootstrap.time, "mktime", lambda value: clock(*value[:6], tzinfo=system_zone).timestamp())
    monkeypatch.setenv("TZ", "GMT-13")
    try:
        assert bootstrap.expiry_time(200) == expected
        assert "TZ" not in os.environ
    finally:
        monkeypatch.undo()
        real_tzset()


def test_ambiguous_system_local_expiry_cannot_change_absolute_deadline(monkeypatch):
    bootstrap = load_bootstrap()
    monkeypatch.setattr(bootstrap.time, "mktime", lambda _wall_time: 3800)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.expiry_time(200)


def fixture(monkeypatch, tmp_path):
    bootstrap = load_bootstrap()
    monkeypatch.setattr(bootstrap, "LEGACY_RETIREMENTS", {})
    config = tmp_path / "config"
    state = tmp_path / "state"
    state.mkdir()
    installed = tmp_path / "lib/trusted_release_server.py"
    keys = tmp_path / "authorized_keys"
    keys.write_text("ssh-ed25519 AAAAExisting unrelated\n")
    keys.chmod(0o600)
    host = tmp_path / "host.pub"
    host.write_text(HOST + " comment\n")
    monkeypatch.setattr(bootstrap, "CONFIG", config)
    monkeypatch.setattr(bootstrap, "STATE", state)
    monkeypatch.setattr(bootstrap, "INSTALLED", installed)
    monkeypatch.setattr(bootstrap, "AUTHORIZED", keys)
    monkeypatch.setattr(bootstrap, "HOST_PUBLIC", host)
    monkeypatch.setattr(bootstrap, "secure", lambda *args, **kwargs: None)
    monkeypatch.setattr(bootstrap.time, "time", lambda: 100)
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "scripts/trusted_release_server.py").write_bytes(b"reviewed fixture")
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "/usr/bin/ssh-keygen" and "-q" in args:
            (config / "loopback.key").write_text("fixture private key")
            (config / "loopback.key.pub").write_text(LOOPBACK + "\n")
        return SimpleNamespace(stdout="", returncode=0)
    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    module = SimpleNamespace(loopback_config=lambda: "Host health\n")
    monkeypatch.setattr(bootstrap, "reviewed_source", lambda sha: (source, module))
    return bootstrap, calls


def test_install_verifies_first_preserves_unrelated_keys_and_does_not_export_private_key(monkeypatch, tmp_path):
    bootstrap, calls = fixture(monkeypatch, tmp_path)
    metadata = bootstrap.AUTHORIZED.stat()
    result = bootstrap.install(SHA, 200, PUBLIC)
    assert result == {"sha": SHA, "state": "INSTALLED"}
    assert "trusted_release_gate.py" in " ".join(calls[0])
    assert "ssh-keygen" in " ".join(calls[1])
    assert bootstrap.AUTHORIZED.read_text().startswith("ssh-ed25519 AAAAExisting unrelated\n")
    after = bootstrap.AUTHORIZED.stat()
    assert (after.st_uid, after.st_gid, after.st_mode) == (metadata.st_uid, metadata.st_gid, metadata.st_mode)
    policy = json.loads((bootstrap.CONFIG / "authorized-release.json").read_text())
    assert set(policy) == {"sha", "expires_at", "executor_sha256"}
    assert (bootstrap.CONFIG / "loopback.key").stat().st_mode & 0o777 == 0o600
    assert (bootstrap.CONFIG / "known_hosts").read_text() == "127.0.0.1 " + HOST + "\n"


def test_gate_failure_happens_before_any_installation_mutation(monkeypatch, tmp_path):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    before = bootstrap.AUTHORIZED.read_bytes()
    def fail(*args, **kwargs):
        raise RuntimeError("CI unavailable")
    monkeypatch.setattr(bootstrap.subprocess, "run", fail)
    with pytest.raises(RuntimeError):
        bootstrap.install(SHA, 200, PUBLIC)
    assert not bootstrap.CONFIG.exists()
    assert not bootstrap.INSTALLED.exists()
    assert bootstrap.AUTHORIZED.read_bytes() == before


@pytest.mark.parametrize("existing", ["policy", "activity"])
def test_existing_authorization_or_unknown_activity_prevents_overwrite(monkeypatch, tmp_path, existing):
    bootstrap, calls = fixture(monkeypatch, tmp_path)
    if existing == "policy":
        bootstrap.CONFIG.mkdir()
        (bootstrap.CONFIG / "authorized-release.json").write_text("existing")
    else:
        release = bootstrap.STATE / SHA
        release.mkdir()
        (release / "started.json").write_text("existing")
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.install(SHA, 200, PUBLIC)
    assert calls == []


def test_revoke_only_removes_exact_managed_lines_and_preserves_metadata(monkeypatch, tmp_path):
    bootstrap, calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    before = bootstrap.AUTHORIZED.stat()
    calls.clear()
    assert bootstrap.revoke(SHA) == {"sha": SHA, "state": "REVOKED"}
    assert bootstrap.AUTHORIZED.read_text() == "ssh-ed25519 AAAAExisting unrelated\n"
    after = bootstrap.AUTHORIZED.stat()
    assert (after.st_uid, after.st_gid, after.st_mode) == (before.st_uid, before.st_gid, before.st_mode)
    assert (bootstrap.CONFIG / "authorized-release.json").exists()
    assert not calls
    assert bootstrap.revoke(SHA)["state"] == "REVOKED"


def test_revoke_wrong_sha_cannot_modify_keys(monkeypatch, tmp_path):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    before = bootstrap.AUTHORIZED.read_bytes()
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.revoke("b" * 40)
    assert bootstrap.AUTHORIZED.read_bytes() == before


def test_reviewed_source_rejects_local_checkout_path_before_git_execution(monkeypatch):
    bootstrap = load_bootstrap()
    monkeypatch.setattr(bootstrap, "secure", lambda *args, **kwargs: None)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.reviewed_source(SHA)


def test_revoke_will_not_race_an_active_launcher(monkeypatch, tmp_path):
    import fcntl
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    before = bootstrap.AUTHORIZED.read_bytes()
    with (bootstrap.STATE / "launcher.lock").open("r+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises((bootstrap.BootstrapError, BlockingIOError)):
            bootstrap.revoke(SHA)
    assert bootstrap.AUTHORIZED.read_bytes() == before


def test_modified_managed_key_options_are_not_silently_ignored(monkeypatch, tmp_path):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    changed = bootstrap.AUTHORIZED.read_bytes() + (PUBLIC + "\n").encode()
    bootstrap.AUTHORIZED.write_bytes(changed)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.revoke(SHA)
    assert bootstrap.AUTHORIZED.read_bytes() == changed


@pytest.mark.parametrize("state", ["STARTED", "NEEDS_OPERATOR"])
@pytest.mark.parametrize("native_claimed", [False, True])
def test_revoke_preserves_all_keys_when_backend_termination_is_unproven(monkeypatch, tmp_path, state, native_claimed):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    release = bootstrap.STATE / SHA
    release.mkdir()
    (release / "started.json").write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    if state == "NEEDS_OPERATOR":
        (release / "completed.json").write_text(json.dumps({"sha": SHA, "state": state}))
    if native_claimed:
        for name in ("build-started.json", "native-started.json"):
            (release / name).write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    markers = {path.name: path.read_bytes() for path in release.iterdir()}
    before = bootstrap.AUTHORIZED.read_bytes()
    metadata = bootstrap.AUTHORIZED.stat()
    with pytest.raises(bootstrap.BootstrapError, match="termination"):
        bootstrap.revoke(SHA)
    assert bootstrap.AUTHORIZED.read_bytes() == before
    after = bootstrap.AUTHORIZED.stat()
    assert (after.st_uid, after.st_gid, after.st_mode) == (metadata.st_uid, metadata.st_gid, metadata.st_mode)
    assert (release / "started.json").exists()
    assert {path.name: path.read_bytes() for path in release.iterdir()} == markers


def test_revoke_after_backend_success_preserves_unrelated_keys_and_native_evidence(monkeypatch, tmp_path):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    release = bootstrap.STATE / SHA
    release.mkdir()
    (release / "started.json").write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    (release / "completed.json").write_text(json.dumps({"sha": SHA, "state": "SUCCEEDED"}))
    (release / "native-started.json").write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    assert bootstrap.revoke(SHA) == {"sha": SHA, "state": "REVOKED"}
    assert bootstrap.AUTHORIZED.read_text() == "ssh-ed25519 AAAAExisting unrelated\n"
    assert (release / "completed.json").exists()
    assert (release / "native-started.json").exists()


@pytest.mark.parametrize("payload", [{"sha": "b" * 40, "state": "SUCCEEDED"}, {"sha": SHA, "state": "FAILED"}, {"sha": SHA, "state": "SUCCEEDED", "extra": True}])
def test_malformed_success_receipt_cannot_authorize_key_removal(monkeypatch, tmp_path, payload):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    release = bootstrap.STATE / SHA
    release.mkdir()
    (release / "started.json").write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    (release / "completed.json").write_text(json.dumps(payload))
    before = bootstrap.AUTHORIZED.read_bytes()
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.revoke(SHA)
    assert bootstrap.AUTHORIZED.read_bytes() == before


NEW_SHA = "b" * 40
NEW_LOOPBACK = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(96, 128))).decode()
LEGACY_SHA = "c" * 40
LEGACY_PUBLIC = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(128, 160))).decode()


def lifecycle_snapshot(bootstrap):
    """Prove a rejected lifecycle operation leaves credentials and claims intact."""
    result = {}
    for root in (bootstrap.STATE, bootstrap.CONFIG, bootstrap.INSTALLED.parent, bootstrap.AUTHORIZED):
        paths = [root, *root.rglob("*")] if root.is_dir() else [root]
        for path in paths:
            info = path.lstat()
            result[str(path)] = (info.st_ino, info.st_mode, path.read_bytes() if path.is_file() else None)
    return result


def preparation_failure_fixture(monkeypatch, tmp_path):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path, succeeded=False)
    workspace = bootstrap.STATE / SHA
    workspace.mkdir(mode=0o700)
    digest = hashlib.sha256(bootstrap.INSTALLED.read_bytes()).hexdigest()
    for name, payload in {
        "started.json": {"sha": SHA, "state": "STARTED"},
        "preparation-started.json": {"sha": SHA, "state": "PREPARING", "executor_sha256": digest},
        "completed.json": {"sha": SHA, "state": "PREPARATION_FAILED"},
    }.items():
        path = workspace / name
        path.write_text(json.dumps(payload))
        path.chmod(0o600)
    return bootstrap, workspace


def test_preparation_failure_can_be_retired_without_rewriting_consumption(monkeypatch, tmp_path):
    bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    before = {p.name: (p.read_bytes(), p.stat().st_ino) for p in workspace.iterdir()}
    assert bootstrap._workspace_evidence(SHA)["state"] == "PREPARATION_FAILED"
    assert bootstrap.rotate(SHA, NEW_SHA, 200, HOST)["state"] == "INSTALLED"
    assert {p.name: (p.read_bytes(), p.stat().st_ino) for p in workspace.iterdir()} == before


@pytest.mark.parametrize("extra", ["deployment-started.json", "prepared.json", "bin", "deployment.env", "build-started.json", "native-started.json"])
@pytest.mark.parametrize("action", ["evidence", "revoke", "rotate"])
def test_preparation_retirement_rejects_any_later_phase_or_vendor_intent(monkeypatch, tmp_path, extra, action):
    bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    (workspace / extra).write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    before = lifecycle_snapshot(bootstrap)
    with pytest.raises(bootstrap.BootstrapError):
        if action == "rotate":
            bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
        elif action == "revoke":
            bootstrap.revoke(SHA)
        else:
            bootstrap._workspace_evidence(SHA)
    assert lifecycle_snapshot(bootstrap) == before


@pytest.mark.parametrize("change", ["missing", "hash", "legacy", "extra_field"])
def test_preparation_retirement_requires_bound_durable_phase_proof(monkeypatch, tmp_path, change):
    bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    marker = workspace / "preparation-started.json"
    if change == "missing":
        marker.unlink()
    elif change == "hash":
        marker.write_text(json.dumps({"sha": SHA, "state": "PREPARING", "executor_sha256": "0" * 64}))
    elif change == "legacy":
        (workspace / "completed.json").write_text(json.dumps({"sha": SHA, "state": "NEEDS_OPERATOR"}))
    else:
        payload = json.loads(marker.read_text())
        payload["extra"] = True
        marker.write_text(json.dumps(payload))
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap._workspace_evidence(SHA)


@pytest.mark.parametrize("action", ["revoke", "rotate"])
@pytest.mark.parametrize("state", ["READY", "SUCCEEDED", "PREPARATION_FAILED"])
def test_lifecycle_holds_existing_build_lock_without_mutation(monkeypatch, tmp_path, action, state):
    if state == "PREPARATION_FAILED":
        bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    else:
        bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path, succeeded=state == "SUCCEEDED")
        workspace = bootstrap.STATE / SHA
        workspace.mkdir(mode=0o700, exist_ok=True)
    for name in ("build-started.json", "native-started.json"):
        (workspace / name).write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    lock = workspace / "build.lock"
    lock.touch(mode=0o600)
    before = lifecycle_snapshot(bootstrap)
    with lock.open("r+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            if action == "rotate":
                bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
            else:
                bootstrap.revoke(SHA)
    assert lifecycle_snapshot(bootstrap) == before


def test_preparation_revoke_rejects_changed_installed_executor(monkeypatch, tmp_path):
    bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    bootstrap.INSTALLED.write_bytes(b"unexpected executor")
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.revoke(SHA)
    assert json.loads((workspace / "completed.json").read_text())["state"] == "PREPARATION_FAILED"


def test_preparation_evidence_binds_nested_content_and_log(monkeypatch, tmp_path):
    bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    source = workspace / "source"
    source.mkdir(mode=0o700)
    nested = source / "partial"
    nested.write_text("original")
    log = workspace / "preparation.log"
    log.write_text("clone failed")
    before = bootstrap._workspace_evidence(SHA)
    nested.write_text("modified")
    after = bootstrap._workspace_evidence(SHA)
    assert after != before
    log.write_text("modified log")
    assert bootstrap._workspace_evidence(SHA) != after


def test_preparation_directory_cannot_be_a_regular_file(monkeypatch, tmp_path):
    bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    (workspace / "home").write_text("not a directory")
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap._workspace_evidence(SHA)


@pytest.mark.parametrize("state", [None, "NEEDS_OPERATOR", "SUCCEEDED"])
def test_review_reset_evidence_gates_retirement_and_revocation(monkeypatch, tmp_path, state):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    workspace = bootstrap.STATE / SHA
    operation_id = "c" * 32
    root = workspace / "review-resets"
    root.mkdir(mode=0o700)
    operation = root / operation_id
    operation.mkdir(mode=0o700)
    (operation / "started.json").write_text(json.dumps({"sha": SHA, "operation_id": operation_id, "state": "STARTED"}))
    (operation / "started.json").chmod(0o600)
    if state:
        (operation / "completed.json").write_text(json.dumps({"sha": SHA, "operation_id": operation_id, "state": state}))
        (operation / "completed.json").chmod(0o600)
    if state == "SUCCEEDED":
        evidence = bootstrap._workspace_evidence(SHA)
        assert "review-resets" in evidence["receipts"]
        assert bootstrap.rotate(SHA, NEW_SHA, 200, HOST)["state"] == "INSTALLED"
    else:
        for action in (lambda: bootstrap._workspace_evidence(SHA), lambda: bootstrap.revoke(SHA)):
            with pytest.raises(bootstrap.BootstrapError):
                action()


def rotation_fixture(monkeypatch, tmp_path, *, succeeded=True):
    bootstrap, calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    if succeeded:
        workspace = bootstrap.STATE / SHA
        workspace.mkdir(mode=0o700)
        for name, state in (("started", "STARTED"), ("completed", "SUCCEEDED"),
                            ("build-started", "STARTED"), ("native-started", "STARTED")):
            path = workspace / f"{name}.json"
            path.write_text(json.dumps({"sha": SHA, "state": state}))
            path.chmod(0o600)
    bootstrap.revoke(SHA)
    (bootstrap.CONFIG / "loopback.key").unlink()
    source, _server = bootstrap.reviewed_source(NEW_SHA)
    monkeypatch.setattr(bootstrap, "canonical_source", lambda sha: source, raising=False)
    monkeypatch.setattr(bootstrap, "BUSINESS_LEASE", tmp_path / "business-lease", raising=False)
    real_run = bootstrap._run
    def run(args, **kwargs):
        if args[0] == "/usr/bin/ps":
            return SimpleNamespace(stdout=f"{os.getpid()} python bootstrap_trusted_release.py\n1 /sbin/init\n")
        result = real_run(args, **kwargs)
        if args[0] == "/usr/bin/ssh-keygen" and "-q" in args:
            (bootstrap.CONFIG / "loopback.key.pub").write_text(NEW_LOOPBACK + "\n")
        return result
    monkeypatch.setattr(bootstrap, "_run", run)
    calls.clear()
    return bootstrap, calls


def test_same_cloud_key_survives_consecutive_versions_without_rewriting_history(monkeypatch, tmp_path):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    original = lifecycle_snapshot(bootstrap)
    assert bootstrap.rotate(SHA, NEW_SHA, 0, PUBLIC)["state"] == "INSTALLED"
    assert set(bootstrap._retired_history()) == {SHA}
    archive, _library = bootstrap._archives(SHA)
    for name in ("cloud.pub", "authorized-release.json"):
        assert (archive / name).read_bytes() == original[str(bootstrap.CONFIG / name)][2]
    assert json.loads((bootstrap.STATE / "retired" / SHA / "intent.json").read_text())["cloud_key_reused"] is True
    first_intent = (bootstrap.STATE / "retired" / SHA / "intent.json").read_bytes()
    bootstrap.revoke(NEW_SHA)
    (bootstrap.CONFIG / "loopback.key").unlink()
    run = bootstrap._run
    def next_keys(args, **kwargs):
        result = run(args, **kwargs)
        if args[0] == "/usr/bin/ssh-keygen" and "-q" in args:
            (bootstrap.CONFIG / "loopback.key.pub").write_text(LEGACY_PUBLIC + "\n")
        return result
    monkeypatch.setattr(bootstrap, "_run", next_keys)
    third = "d" * 40
    assert bootstrap.rotate(NEW_SHA, third, 0, PUBLIC)["state"] == "INSTALLED"
    assert set(bootstrap._retired_history()) == {SHA, NEW_SHA}
    assert (bootstrap.STATE / "retired" / SHA / "intent.json").read_bytes() == first_intent
    assert bootstrap.AUTHORIZED.read_text().count(PUBLIC) == 1
    bootstrap.revoke(third)
    (bootstrap.CONFIG / "loopback.key").unlink()
    assert PUBLIC not in bootstrap.AUTHORIZED.read_text()
    assert set(bootstrap._retired_history()) == {SHA, NEW_SHA}
    for used in (SHA, NEW_SHA, third):
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap.rotate(third, used, 0, PUBLIC)


@pytest.mark.parametrize("fault", ["bare-key", "duplicate", "executor", "policy-sha", "finite", "reuse-audit", "loopback"])
def test_history_does_not_accept_unproven_persistent_identity(monkeypatch, tmp_path, fault):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    bootstrap.rotate(SHA, NEW_SHA, 0, PUBLIC)
    if fault == "bare-key":
        bootstrap.AUTHORIZED.write_text(PUBLIC + "\n")
    elif fault == "duplicate":
        bootstrap.AUTHORIZED.write_text(bootstrap.AUTHORIZED.read_text() + PUBLIC + "\n")
    elif fault == "executor":
        bootstrap.INSTALLED.write_bytes(b"modified")
    elif fault in {"policy-sha", "finite"}:
        path = bootstrap.CONFIG / "authorized-release.json"
        data = json.loads(path.read_text())
        data["sha" if fault == "policy-sha" else "expires_at"] = SHA if fault == "policy-sha" else 200
        path.write_text(json.dumps(data))
    elif fault == "reuse-audit":
        path = bootstrap.STATE / "retired" / SHA / "intent.json"
        data = json.loads(path.read_text())
        del data["cloud_key_reused"]
        path.write_text(json.dumps(data))
    else:
        bootstrap.AUTHORIZED.write_text(bootstrap.AUTHORIZED.read_text() + LOOPBACK + "\n")
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap._retired_history()


@pytest.mark.parametrize("public", [PUBLIC, LOOPBACK, NEW_LOOPBACK])
def test_persistent_mode_cannot_resurrect_replaced_or_loopback_keys(monkeypatch, tmp_path, public):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    bootstrap.rotate(SHA, NEW_SHA, 0, HOST)
    bootstrap.revoke(NEW_SHA)
    (bootstrap.CONFIG / "loopback.key").unlink()
    before = lifecycle_snapshot(bootstrap)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.rotate(NEW_SHA, "d" * 40, 0, public)
    assert lifecycle_snapshot(bootstrap) == before


@pytest.mark.parametrize("succeeded", [True, False])
def test_rotation_preserves_old_install_and_once_evidence(monkeypatch, tmp_path, succeeded):
    bootstrap, calls = rotation_fixture(monkeypatch, tmp_path, succeeded=succeeded)
    old_config = {p.name: (p.read_bytes(), p.stat().st_ino) for p in bootstrap.CONFIG.iterdir()}
    old_code = bootstrap.INSTALLED.stat().st_ino
    old_markers = {p.name: p.read_bytes() for p in (bootstrap.STATE / SHA).iterdir()} if succeeded else {}
    lock_inode = (bootstrap.STATE / "launcher.lock").stat().st_ino
    assert bootstrap.rotate(SHA, NEW_SHA, 200, HOST) == {"sha": NEW_SHA, "state": "INSTALLED", "retired_sha": SHA}
    config_archive = bootstrap.CONFIG.with_name(bootstrap.CONFIG.name + ".retired-" + SHA)
    code_archive = bootstrap.INSTALLED.parent.with_name(bootstrap.INSTALLED.parent.name + ".retired-" + SHA)
    assert {p.name: (p.read_bytes(), p.stat().st_ino) for p in config_archive.iterdir()} == old_config
    assert (code_archive / bootstrap.INSTALLED.name).stat().st_ino == old_code
    assert (bootstrap.STATE / "launcher.lock").stat().st_ino == lock_inode
    if succeeded:
        assert {p.name: p.read_bytes() for p in (bootstrap.STATE / SHA).iterdir()} == old_markers
    assert json.loads((bootstrap.CONFIG / "authorized-release.json").read_bytes())["sha"] == NEW_SHA
    assert "trusted_release_gate.py" in " ".join(calls[0])
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.rotate(NEW_SHA, NEW_SHA, 200, PUBLIC)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.install(NEW_SHA, 200, PUBLIC)


def legacy_fixture(monkeypatch, tmp_path):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    entry = bootstrap.STATE / "retired" / LEGACY_SHA
    entry.mkdir(parents=True, mode=0o700)
    shutil.copytree(bootstrap.CONFIG, entry / "config")
    shutil.copytree(bootstrap.INSTALLED.parent, entry / "executor")
    policy_path = entry / "config/authorized-release.json"
    policy = json.loads(policy_path.read_bytes())
    policy["sha"] = LEGACY_SHA
    policy_path.write_text(json.dumps(policy))
    (entry / "config/cloud.pub").write_text(LEGACY_PUBLIC)
    evidence = {"installation": bootstrap._installation_evidence(LEGACY_SHA, entry / "config", entry / "executor"),
                "workspace": bootstrap._workspace_evidence(LEGACY_SHA)}
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    monkeypatch.setattr(bootstrap, "LEGACY_RETIREMENTS", {LEGACY_SHA: digest}, raising=False)
    return bootstrap, entry


def test_rotation_accepts_only_pinned_legacy_archive_without_rewriting_it(monkeypatch, tmp_path):
    bootstrap, entry = legacy_fixture(monkeypatch, tmp_path)
    before = {str(p.relative_to(entry)): (p.read_bytes(), p.stat().st_ino)
              for p in entry.rglob("*") if p.is_file()}
    assert bootstrap.rotate(SHA, NEW_SHA, 200, HOST)["state"] == "INSTALLED"
    assert {str(p.relative_to(entry)): (p.read_bytes(), p.stat().st_ino)
            for p in entry.rglob("*") if p.is_file()} == before
    assert set(bootstrap._retired_history()) == {SHA, LEGACY_SHA}


@pytest.mark.parametrize("fault", ["unknown-sha", "digest", "changed-config", "private-key", "extra",
                                 "workspace", "authorized-key", "reuse-sha", "reuse-key", "missing", "missing-root"])
def test_legacy_archive_faults_block_before_authorization_or_retirement(monkeypatch, tmp_path, fault):
    bootstrap, entry = legacy_fixture(monkeypatch, tmp_path)
    new_sha, public = NEW_SHA, HOST
    if fault == "unknown-sha":
        monkeypatch.setattr(bootstrap, "LEGACY_RETIREMENTS", {})
    elif fault == "digest":
        monkeypatch.setattr(bootstrap, "LEGACY_RETIREMENTS", {LEGACY_SHA: "0" * 64})
    elif fault == "changed-config":
        (entry / "config/loopback.conf").write_text("changed")
    elif fault == "private-key":
        (entry / "config/loopback.key").write_text("unexpected")
    elif fault == "extra":
        (entry / "intent.json").write_text("{}")
    elif fault == "workspace":
        (bootstrap.STATE / LEGACY_SHA).mkdir()
    elif fault == "authorized-key":
        bootstrap.AUTHORIZED.write_text(LEGACY_PUBLIC + "\n")
    elif fault == "reuse-sha":
        new_sha = LEGACY_SHA
    elif fault in {"missing", "missing-root"}:
        shutil.rmtree(entry if fault == "missing" else entry.parent)
    else:
        public = LEGACY_PUBLIC
    before = bootstrap.AUTHORIZED.read_bytes()
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.rotate(SHA, new_sha, 200, public)
    assert bootstrap.AUTHORIZED.read_bytes() == before
    assert not (bootstrap.STATE / "retired" / SHA).exists()
    assert bootstrap.CONFIG.exists()


@pytest.mark.parametrize("fault", ["wrong-old", "same-sha", "authorized", "private-key", "code-hash",
    "extra-config", "extra-code", "symlink", "ready-vendor-claimed", "started", "failed", "duplicate-json", "lease",
    "foreign-started", "new-workspace", "archive-exists", "process", "unknown-process"])
def test_rotation_fails_closed_before_retirement(monkeypatch, tmp_path, fault):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    old, new = SHA, NEW_SHA
    if fault == "wrong-old":
        old = "c" * 40
    elif fault == "same-sha":
        new = SHA
    elif fault == "authorized":
        bootstrap.AUTHORIZED.write_text(PUBLIC + "\n")
    elif fault == "private-key":
        (bootstrap.CONFIG / "loopback.key").write_text("retained")
    elif fault == "code-hash":
        bootstrap.INSTALLED.write_text("modified")
    elif fault in {"extra-config", "extra-code"}:
        parent = bootstrap.CONFIG if fault == "extra-config" else bootstrap.INSTALLED.parent
        (parent / "unknown").write_text("unreviewed")
    elif fault == "symlink":
        path = bootstrap.CONFIG / "cloud.pub"
        path.unlink()
        path.symlink_to(tmp_path / "missing")
    elif fault == "ready-vendor-claimed":
        # Upload may finish before backend even starts; vendor consumption is
        # never equivalent to a safely unused authorization for rotation.
        (bootstrap.STATE / SHA / "started.json").unlink()
        (bootstrap.STATE / SHA / "completed.json").unlink()
    elif fault == "started":
        (bootstrap.STATE / SHA / "completed.json").unlink()
    elif fault == "failed":
        (bootstrap.STATE / SHA / "completed.json").write_text(json.dumps({"sha": SHA, "state": "NEEDS_OPERATOR"}))
    elif fault == "duplicate-json":
        (bootstrap.STATE / SHA / "completed.json").write_text('{"sha":"' + SHA + '","state":"FAILED","state":"SUCCEEDED"}')
    elif fault == "lease":
        bootstrap.BUSINESS_LEASE.symlink_to(tmp_path / "missing")
    elif fault == "foreign-started":
        other = bootstrap.STATE / ("c" * 40)
        other.mkdir()
        (other / "started.json").write_text("unknown")
    elif fault == "new-workspace":
        (bootstrap.STATE / NEW_SHA).mkdir()
    elif fault == "archive-exists":
        bootstrap.CONFIG.with_name(bootstrap.CONFIG.name + ".retired-" + SHA).mkdir()
    elif fault in {"process", "unknown-process"}:
        real_run = bootstrap._run
        def run(args, **kwargs):
            if args[0] == "/usr/bin/ps":
                return SimpleNamespace(stdout="777 bash /tmp/health-app-backup-preflight-1-2/rollback_release.sh\n" if fault == "process" else "")
            return real_run(args, **kwargs)
        monkeypatch.setattr(bootstrap, "_run", run)
    before = bootstrap.AUTHORIZED.read_bytes()
    markers = {p.name: (p.read_bytes(), p.stat().st_ino) for p in (bootstrap.STATE / SHA).iterdir()}
    with pytest.raises((bootstrap.BootstrapError, OSError)):
        bootstrap.rotate(old, new, 200, HOST)
    assert bootstrap.CONFIG.exists()
    assert bootstrap.INSTALLED.exists()
    assert bootstrap.AUTHORIZED.read_bytes() == before
    assert not (bootstrap.STATE / "retired").exists()
    assert {p.name: (p.read_bytes(), p.stat().st_ino) for p in (bootstrap.STATE / SHA).iterdir()} == markers


def test_rotation_requires_nonblocking_global_lock(monkeypatch, tmp_path):
    import fcntl
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    with (bootstrap.STATE / "launcher.lock").open("r+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises((bootstrap.BootstrapError, BlockingIOError)):
            bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert bootstrap.CONFIG.exists()
    assert not (bootstrap.STATE / "retired").exists()


@pytest.mark.parametrize("point", ["first-move", "second-move", "new-install", "completion"])
def test_interrupted_rotation_is_not_resumable_and_keeps_audit(monkeypatch, tmp_path, point):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    rename, write = bootstrap.os.rename, bootstrap._write
    def move(source, target):
        if (point == "first-move" and source == bootstrap.CONFIG) or (point == "second-move" and source == bootstrap.INSTALLED.parent):
            raise OSError("injected interruption")
        return rename(source, target)
    def fail_write(path, data):
        if (point == "new-install" and path == bootstrap.INSTALLED) or (point == "completion" and path == bootstrap.STATE / "retired" / SHA / "completed.json"):
            raise OSError("injected interruption")
        return write(path, data)
    monkeypatch.setattr(bootstrap.os, "rename", move)
    monkeypatch.setattr(bootstrap, "_write", fail_write)
    with pytest.raises(OSError):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert (bootstrap.STATE / "retired" / SHA / "intent.json").exists()
    assert (bootstrap.STATE / SHA / "started.json").exists()
    monkeypatch.setattr(bootstrap.os, "rename", rename)
    monkeypatch.setattr(bootstrap, "_write", write)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.install(NEW_SHA, 200, HOST)
    assert bootstrap.AUTHORIZED.read_text() == "ssh-ed25519 AAAAExisting unrelated\n"


@pytest.mark.parametrize("fault", ["hash", "inventory", "receipt", "missing-completion"])
def test_retired_history_is_revalidated_not_a_blanket_started_exemption(monkeypatch, tmp_path, fault):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    bootstrap.revoke(NEW_SHA)
    (bootstrap.CONFIG / "loopback.key").unlink()
    archived_config, archived_library = bootstrap._archives(SHA)
    if fault == "hash":
        (archived_library / bootstrap.INSTALLED.name).write_text("changed")
    elif fault == "inventory":
        (archived_config / "unknown").write_text("changed")
    elif fault == "receipt":
        (bootstrap.STATE / SHA / "started.json").unlink()
    else:
        (bootstrap.STATE / "retired" / SHA / "completed.json").unlink()
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.rotate(NEW_SHA, "c" * 40, 200, PUBLIC)
    assert bootstrap.CONFIG.exists()


def test_rotation_verifies_new_source_and_gate_before_mutation(monkeypatch, tmp_path):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    seen = []
    reviewed = bootstrap.reviewed_source
    def source(sha):
        seen.append(sha)
        return reviewed(sha)
    monkeypatch.setattr(bootstrap, "reviewed_source", source)
    def fail(*args, **kwargs):
        raise RuntimeError("CI unavailable")
    monkeypatch.setattr(bootstrap, "_run", fail)
    with pytest.raises(RuntimeError):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert seen == [NEW_SHA]
    assert bootstrap.CONFIG.exists()
    assert not (bootstrap.STATE / "retired").exists()


def test_both_modified_policy_and_executor_cannot_replace_canonical_hash(monkeypatch, tmp_path):
    import hashlib
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    bootstrap.INSTALLED.write_bytes(b"unreviewed")
    policy_file = bootstrap.CONFIG / "authorized-release.json"
    policy = json.loads(policy_file.read_text())
    policy["executor_sha256"] = hashlib.sha256(b"unreviewed").hexdigest()
    policy_file.write_text(json.dumps(policy))
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert bootstrap.CONFIG.exists()


def test_rotation_will_not_reauthorize_old_loopback_identity(monkeypatch, tmp_path):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    run = bootstrap._run
    def reused(args, **kwargs):
        result = run(args, **kwargs)
        if args[0] == "/usr/bin/ssh-keygen" and "-q" in args:
            (bootstrap.CONFIG / "loopback.key.pub").write_text(LOOPBACK + "\n")
        return result
    monkeypatch.setattr(bootstrap, "_run", reused)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    assert bootstrap.AUTHORIZED.read_text() == "ssh-ed25519 AAAAExisting unrelated\n"


def test_consecutive_rotation_preserves_prior_audit_and_rejects_all_used_shas(monkeypatch, tmp_path):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
    bootstrap.revoke(NEW_SHA)
    (bootstrap.CONFIG / "loopback.key").unlink()
    before = (bootstrap.STATE / "retired" / SHA / "intent.json").read_bytes()
    for reused in (SHA, NEW_SHA):
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap.rotate(NEW_SHA, reused, 200, PUBLIC)
    fresh = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(128, 160))).decode()
    fresh_loopback = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(160, 192))).decode()
    run = bootstrap._run
    def next_keys(args, **kwargs):
        result = run(args, **kwargs)
        if args[0] == "/usr/bin/ssh-keygen" and "-q" in args:
            (bootstrap.CONFIG / "loopback.key.pub").write_text(fresh_loopback + "\n")
        return result
    monkeypatch.setattr(bootstrap, "_run", next_keys)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.rotate(NEW_SHA, "c" * 40, 200, PUBLIC)
    assert bootstrap.rotate(NEW_SHA, "c" * 40, 200, fresh)["state"] == "INSTALLED"
    assert (bootstrap.STATE / "retired" / SHA / "intent.json").read_bytes() == before
    assert set(bootstrap._retired_history()) == {SHA, NEW_SHA}


@pytest.mark.parametrize("parent_shell", [False, True])
def test_idle_probe_accepts_ssh_exec_but_not_a_lingering_release_shell(monkeypatch, tmp_path, parent_shell):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    command = (f"/usr/bin/python3 -I /var/lib/reva-release/bootstrap/{NEW_SHA}/source/"
               f"scripts/bootstrap_trusted_release.py rotate --retire-sha {SHA} --sha {NEW_SHA}")
    processes = f"1 /sbin/init\n400 sshd: root@notty\n{os.getpid()} {command}\n402 /usr/bin/ps -e -ww -o pid= -o args=\n"
    if parent_shell:
        processes += f"403 /bin/sh -c {command}\n"
    monkeypatch.setattr(bootstrap, "_run", lambda *args, **kwargs: SimpleNamespace(stdout=processes))
    if parent_shell:
        with pytest.raises(bootstrap.BootstrapError, match="process"):
            bootstrap._assert_idle()
    else:
        bootstrap._assert_idle()


@pytest.mark.parametrize("bad", ["owner", "permissions", "symlink", "hardlink"])
def test_retirement_inventory_checks_real_root_metadata(monkeypatch, bad):
    import stat
    bootstrap = load_bootstrap()
    target = Path("/root/retirement-test/config")
    def metadata(path):
        mode, uid, links = stat.S_IFDIR | 0o700, 0, 1
        if path == target:
            if bad == "owner":
                uid = 1234
            elif bad == "permissions":
                mode = stat.S_IFDIR | 0o777
            elif bad == "symlink":
                mode = stat.S_IFLNK | 0o777
            else:
                mode, links = stat.S_IFREG | 0o600, 2
        return os.stat_result((mode, 1, 1, links, uid, 0, 0, 0, 0, 0))
    monkeypatch.setattr(Path, "lstat", metadata)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap._inventory(target, set())


def test_native_closure_cannot_conflict_with_other_closure(monkeypatch,tmp_path):
    bootstrap,_calls=fixture(monkeypatch,tmp_path)
    for name in ('native-only-closures','partial-laya-closures'):
        (bootstrap.STATE/name/SHA).mkdir(parents=True)
    with pytest.raises(bootstrap.BootstrapError,match='conflicting'):
        bootstrap._workspace_evidence(SHA)


def test_native_closure_dispatches_distinct_terminal_with_historical_flag(monkeypatch,tmp_path):
    bootstrap,_calls=fixture(monkeypatch,tmp_path)
    (bootstrap.STATE/'native-only-closures'/SHA).mkdir(parents=True)
    source=tmp_path/'canonical';source.mkdir()
    (source/'native_release_retirement.py').write_text('# fixture\n')
    bootstrap.__file__=str(source/'bootstrap_trusted_release.py')
    monkeypatch.setattr(bootstrap,'secure',lambda *a,**k:None)
    received=[]
    def closed(b,sha,receipt,*,historical):
        received.append((sha,receipt,historical))
        return {'state':'CLOSED_NATIVE_ONLY_VENDOR_UPLOAD'}
    imported=SimpleNamespace(closed_evidence=closed)
    monkeypatch.setattr(bootstrap.importlib.util,'module_from_spec',lambda spec:imported)
    monkeypatch.setattr(bootstrap.importlib.util,'spec_from_file_location',lambda *a:SimpleNamespace(
        loader=SimpleNamespace(exec_module=lambda module:None)))
    monkeypatch.setattr(bootstrap,'sys',SimpleNamespace(modules={bootstrap.__name__:bootstrap}))
    assert bootstrap._workspace_evidence(SHA,recovery_receipt='c'*64,historical=True)=={'state':'CLOSED_NATIVE_ONLY_VENDOR_UPLOAD'}
    assert received==[(SHA,'c'*64,True)]


@pytest.mark.parametrize('fault', [None, 'missing_receipt', 'not_native', 'inspection', 'drift'])
def test_explicit_finalized_native_rotation_keeps_real_receipts_and_history(monkeypatch, tmp_path, fault):
    bootstrap, _calls = rotation_fixture(monkeypatch, tmp_path)
    monkeypatch.setitem(bootstrap.sys.modules, bootstrap.__name__, bootstrap)
    proofs = []
    workspace = {'state': 'SUCCEEDED' if fault == 'not_native' else 'CLOSED_NATIVE_ONLY_VENDOR_UPLOAD'}
    monkeypatch.setattr(bootstrap, '_workspace_evidence', lambda sha, **kw: (proofs.append(kw) or workspace))
    count = []
    def inspect(*args):
        count.append(True)
        if fault == 'inspection': raise bootstrap.BootstrapError('live proof rejected')
        return {'proof': len(count) if fault == 'drift' else 1}
    module = SimpleNamespace(inspect=inspect, validate_saved=lambda proof, sha: None)
    monkeypatch.setattr(bootstrap, '_finalized_advance_module', lambda: module)
    record = bootstrap.STATE / 'retired' / SHA
    if fault:
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap.rotate(SHA, NEW_SHA, 0, PUBLIC,
                recovery_receipt=None if fault == 'missing_receipt' else 'c' * 64,
                finalized_production_sha='d' * 40)
        assert record.exists() == (fault == 'drift')
        assert (bootstrap.CONFIG / 'authorized-release.json').exists()
    else:
        result = bootstrap.rotate(SHA, NEW_SHA, 0, PUBLIC,
            recovery_receipt='c' * 64, finalized_production_sha='d' * 40)
        assert result['state'] == 'INSTALLED'
        intent = json.loads((record / 'intent.json').read_text())
        assert intent['finalized_native_advance'] == {'proof': 1}
        module.inspect = lambda *args: pytest.fail('history must not depend on future live state')
        assert SHA in bootstrap._retired_history()
        assert not (bootstrap.STATE / NEW_SHA / 'completed.json').exists()
    assert all(p.get('historical') is True for p in proofs)


@pytest.mark.parametrize('action', ['install', 'rotate'])
def test_backend_bootstrap_uses_bound_admission_before_keys(monkeypatch, tmp_path, action):
    if action == 'install':
        bootstrap, calls = fixture(monkeypatch, tmp_path)
        bootstrap.install(SHA, 200, PUBLIC, backend_ci=True)
    else:
        bootstrap, calls = rotation_fixture(monkeypatch, tmp_path, succeeded=True)
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST, backend_ci=True)
    assert calls[0][1:4] == ['-I', '-S', '-B']
    assert calls[0][4].endswith('/scripts/trusted_backend_admission.py')
    assert '--base' not in calls[0]


@pytest.mark.parametrize('extra', [{'recovery_receipt': 'unsafe'}, {'finalized_production_sha': SHA}])
def test_backend_bootstrap_cannot_replace_recovery_gate(monkeypatch, tmp_path, extra):
    bootstrap, calls = rotation_fixture(monkeypatch, tmp_path, succeeded=True)
    before = lifecycle_snapshot(bootstrap)
    with pytest.raises(bootstrap.BootstrapError, match='cannot replace'):
        bootstrap.rotate(SHA, NEW_SHA, 200, HOST, backend_ci=True, **extra)
    assert not calls
    assert lifecycle_snapshot(bootstrap) == before


def test_retained_candidate_closure_conflicts_with_every_other_closure(monkeypatch, tmp_path):
    bootstrap, _ = fixture(monkeypatch, tmp_path)
    (bootstrap.STATE / 'retained-candidate-closures' / SHA).mkdir(parents=True)
    (bootstrap.STATE / 'native-only-closures' / SHA).mkdir(parents=True)
    with pytest.raises(bootstrap.BootstrapError, match='conflicting'):
        bootstrap._workspace_evidence(SHA)


def test_retained_candidate_dispatch_preserves_historical_mode(monkeypatch, tmp_path):
    bootstrap, _ = fixture(monkeypatch, tmp_path)
    (bootstrap.STATE / 'retained-candidate-closures' / SHA).mkdir(parents=True)
    source = tmp_path / 'canonical'; source.mkdir()
    (source / 'retained_candidate_retirement.py').write_text('# fixture\n')
    bootstrap.__file__ = str(source / 'bootstrap_trusted_release.py')
    monkeypatch.setattr(bootstrap, 'secure', lambda *a, **k: None)
    received = []
    def closed(b, sha, receipt, *, historical):
        received.append((sha, receipt, historical))
        return {'state': 'CLOSED_RETAINED_CANDIDATE_FAILURE'}
    imported = SimpleNamespace(closed_evidence=closed)
    monkeypatch.setattr(bootstrap.importlib.util, 'module_from_spec', lambda spec: imported)
    monkeypatch.setattr(bootstrap.importlib.util, 'spec_from_file_location', lambda *a: SimpleNamespace(
        loader=SimpleNamespace(exec_module=lambda module: None)))
    monkeypatch.setattr(bootstrap, 'sys', SimpleNamespace(modules={bootstrap.__name__: bootstrap}))
    assert bootstrap._workspace_evidence(SHA, recovery_receipt='c'*64, historical=True) == {
        'state': 'CLOSED_RETAINED_CANDIDATE_FAILURE'}
    assert received == [(SHA, 'c'*64, True)]


def test_retained_candidate_rotation_preserves_failure_and_blocks_reuse(monkeypatch, tmp_path):
    bootstrap, _ = rotation_fixture(monkeypatch, tmp_path)
    completed = bootstrap.STATE / SHA / 'completed.json'
    completed.write_text(json.dumps({'sha': SHA, 'state': 'NEEDS_OPERATOR'}))
    original = completed.read_bytes()
    workspace = {'state': 'CLOSED_RETAINED_CANDIDATE_FAILURE', 'closure': 'e'*64}
    proofs = []
    def inspect(sha, **kwargs):
        proofs.append(kwargs)
        assert kwargs.get('recovery_receipt') == 'c'*64
        return workspace
    monkeypatch.setattr(bootstrap, '_workspace_evidence', inspect)
    result = bootstrap.rotate(SHA, NEW_SHA, 200, HOST, recovery_receipt='c'*64)
    assert result['state'] == 'INSTALLED'
    assert completed.read_bytes() == original
    assert not (bootstrap.STATE / NEW_SHA / 'completed.json').exists()
    assert bootstrap._retired_history()[SHA]['workspace'] == workspace
    assert any(p.get('historical') is True for p in proofs)
    with pytest.raises(bootstrap.BootstrapError, match='already used'):
        bootstrap._assert_fresh_sha(SHA, bootstrap._retired_history())
