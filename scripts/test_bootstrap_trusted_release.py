"""Bootstrap tests run only in temporary local fixtures, never production."""

import base64
import importlib.util
import json
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


def test_key_lines_are_fixed_expiring_and_loopback_cannot_be_remote():
    bootstrap = load_bootstrap()
    cloud, loopback = bootstrap.key_lines(200, PUBLIC, "ssh-ed25519 AAAA")
    assert cloud == 'command="/usr/bin/python3 -I /usr/local/lib/reva-release/trusted_release_server.py",restrict,expiry-time="19700101000320Z" ' + PUBLIC
    assert loopback == 'from="127.0.0.1",restrict,expiry-time="19700101000320Z" ssh-ed25519 AAAA'


def fixture(monkeypatch, tmp_path):
    bootstrap = load_bootstrap()
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
