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
    ("main", 200, PUBLIC), (SHA, 100, PUBLIC), (SHA, 100 + 28801, PUBLIC),
    (SHA, True, PUBLIC), (SHA, 200, PUBLIC + " comment"),
    (SHA, 200, 'command="id" ' + PUBLIC), (SHA, 200, PUBLIC + "\n"),
    (SHA, 200, "ssh-ed25519 AAAAFixture"),
    (SHA, 200, "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x1f" + bytes(range(31))).decode()),
    (SHA, 200, "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(33))).decode()),
])
def test_install_inputs_are_closed_and_expire_within_eight_hours(sha, expiry, public):
    bootstrap = load_bootstrap()
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.validate_install(sha, expiry, public, now=100)


def test_valid_install_inputs_are_exact_not_normalized():
    bootstrap = load_bootstrap()
    bootstrap.validate_install(SHA, 100 + 28800, PUBLIC, now=100)


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
def test_revoke_preserves_all_keys_when_backend_termination_is_unproven(monkeypatch, tmp_path, state):
    bootstrap, _calls = fixture(monkeypatch, tmp_path)
    bootstrap.install(SHA, 200, PUBLIC)
    release = bootstrap.STATE / SHA
    release.mkdir()
    (release / "started.json").write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    if state == "NEEDS_OPERATOR":
        (release / "completed.json").write_text(json.dumps({"sha": SHA, "state": state}))
    before = bootstrap.AUTHORIZED.read_bytes()
    metadata = bootstrap.AUTHORIZED.stat()
    with pytest.raises(bootstrap.BootstrapError, match="termination"):
        bootstrap.revoke(SHA)
    assert bootstrap.AUTHORIZED.read_bytes() == before
    after = bootstrap.AUTHORIZED.stat()
    assert (after.st_uid, after.st_gid, after.st_mode) == (metadata.st_uid, metadata.st_gid, metadata.st_mode)
    assert (release / "started.json").exists()


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
def test_preparation_retirement_rejects_any_later_phase_or_vendor_intent(monkeypatch, tmp_path, extra):
    bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    (workspace / extra).write_text("{}")
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap._workspace_evidence(SHA)


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
def test_preparation_lifecycle_holds_existing_build_lock(monkeypatch, tmp_path, action):
    bootstrap, workspace = preparation_failure_fixture(monkeypatch, tmp_path)
    lock = workspace / "build.lock"
    lock.touch(mode=0o600)
    with lock.open("r+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            if action == "rotate":
                bootstrap.rotate(SHA, NEW_SHA, 200, HOST)
            else:
                bootstrap.revoke(SHA)


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
    "extra-config", "extra-code", "symlink", "started", "failed", "duplicate-json", "lease",
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
    with pytest.raises((bootstrap.BootstrapError, OSError)):
        bootstrap.rotate(old, new, 200, HOST)
    assert bootstrap.CONFIG.exists()
    assert bootstrap.INSTALLED.exists()
    assert bootstrap.AUTHORIZED.read_bytes() == before
    assert not (bootstrap.STATE / "retired").exists()


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
