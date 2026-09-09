"""Offline tests: closure must not turn restored service into release success."""
import importlib.util
import json
import hashlib
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    path = Path(__file__).with_name("contained_release_retirement.py")
    spec = importlib.util.spec_from_file_location("closure_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Adapter:
    def __init__(self, root):
        self.record = root / "closure"
        self.events = []
        self.evidence = {"old_sha": "a" * 40, "closing_sha": "b" * 40}

    def inspect(self):
        self.events.append("inspect")
        return self.evidence.copy()

    def archive_and_revoke(self, evidence):
        assert (self.record / "intent.json").is_file()
        self.events.append("mutation")

    def verify_closed(self, evidence):
        self.events.append("postcondition")
        return {"installation": {}, "archives": {}}


def test_inspection_is_read_only(tmp_path):
    m, a = load(), Adapter(tmp_path)
    result = m.close_transaction(a)
    assert result["state"] == "INSPECTED_RESTORED_RELEASE"
    assert not a.record.exists()
    assert a.events == ["inspect"]


def test_wrong_digest_does_not_consume_operation(tmp_path):
    m, a = load(), Adapter(tmp_path)
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, "0" * 64)
    assert not a.record.exists()


def test_closed_receipt_is_not_release_success_and_cannot_replay(tmp_path):
    m, a = load(), Adapter(tmp_path)
    digest = m.close_transaction(a)["evidence_sha256"]
    result = m.close_transaction(a, digest)
    assert result["state"] == "CLOSED_RESTORED_RELEASE"
    assert len(result["receipt"]) == 64
    intent = json.loads((a.record / "intent.json").read_text())
    assert result["receipt"] not in (a.record / "intent.json").read_text()
    assert intent["receipt_sha256"] == m.hashlib.sha256(result["receipt"].encode()).hexdigest()
    assert a.events[-3:] == ["inspect", "mutation", "postcondition"]
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, digest)


@pytest.mark.parametrize("point", ["intent", "recheck", "mutation", "postcondition", "completion"])
def test_failure_is_durable_and_never_issues_receipt(tmp_path, monkeypatch, point):
    m, a = load(), Adapter(tmp_path)
    digest = m.close_transaction(a)["evidence_sha256"]
    write = m._write
    def fault_write(path, value):
        if (point == "intent" and path.name == "intent.json") or (point == "completion" and path.name == "completed.json"):
            raise OSError("injected fsync failure")
        write(path, value)
        if point == "recheck" and path.name == "intent.json":
            a.evidence["drift"] = True
    monkeypatch.setattr(m, "_write", fault_write)
    if point in {"mutation", "postcondition"}:
        method = "archive_and_revoke" if point == "mutation" else "verify_closed"
        monkeypatch.setattr(a, method, lambda *args: (_ for _ in ()).throw(OSError("injected failure")))
    with pytest.raises((OSError, m.ClosureError)):
        m.close_transaction(a, digest)
    assert a.record.exists()
    assert not (a.record / "completed.json").exists()
    if point in {"intent", "recheck"}:
        assert "mutation" not in a.events
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, digest)


def test_visible_completed_without_receipt_cannot_authorize_rotation():
    m = load()
    intent = {"receipt_sha256": m.hashlib.sha256(b"c" * 64).hexdigest()}
    for invalid in (None, "", "d" * 64, True, "c" * 63):
        with pytest.raises(m.ClosureError):
            m.verify_receipt(intent, invalid)
    m.verify_receipt(intent, "c" * 64)


def test_archival_names_cover_exact_sealed_stage():
    m = load()
    snapshot = {"stage": {name: {"sha256": name} for name in (
        "lease", "token", "label", "stage", "started_at", "pointer", "directory", "live_env",
        "manifest", "backend.env.rollback", "backend.env.candidate", "script.py")}}
    expected = m._expected_archives(snapshot)
    assert set(expected["lease"]) == {"token", "label", "stage", "started_at"}
    assert set(expected["stage"]) == {"staged.sha256", "backend.env.rollback", "backend.env.candidate", "script.py"}


def test_readiness_split_retains_original_lease_checks(monkeypatch):
    spec = importlib.util.spec_from_file_location("proof_for_closure", Path(__file__).with_name("contained_recovery_proof.py"))
    p = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p)
    instance = p.RecoveryProof.__new__(p.RecoveryProof)
    events = []
    instance._assert_original_lease = lambda: events.append("lease")
    instance.running_services_snapshot = lambda: events.append("services") or {"ready": True}
    assert instance.running_snapshot() == {"ready": True}
    assert events == ["lease", "services", "lease"]


def proof_fixture(tmp_path, monkeypatch):
    """Real files and receipts; OS-root ownership is normalized only in fixture."""
    m = load()
    old, closing, production, restored_sha = (c * 40 for c in "abcd")
    state = tmp_path / "state"
    state.mkdir()
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    library = tmp_path / "library"
    library.mkdir(mode=0o700)
    workspace = state / old
    workspace.mkdir(mode=0o700)
    lease = tmp_path / "lock"
    lease.mkdir(mode=0o700)
    stage = tmp_path / "sealed"
    stage.mkdir(mode=0o700)
    monkeypatch.setattr(m, "ACTIVE_LEASE", lease)
    monkeypatch.setattr(m, "VOLATILE_ROOT", tmp_path)
    monkeypatch.setattr(m, "_move_no_clobber", os.rename)
    def read(path):
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_nlink != 1:
            raise m.ClosureError("fixture rejects linked or non-file input")
        raw = path.read_bytes()
        return raw, {"dev": info.st_dev, "ino": info.st_ino, "uid": 0, "gid": 0,
                     "mode": stat.S_IMODE(info.st_mode), "sha256": hashlib.sha256(raw).hexdigest()}
    monkeypatch.setattr(m, "_file", lambda b, p: read(p))
    def private(b, path):
        if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise m.ClosureError("private fixture required")
    monkeypatch.setattr(m, "_private_directory", private)
    def inventory(path, names):
        if {p.name for p in path.iterdir()} != set(names):
            raise m.ClosureError("fixture inventory drift")
        return {".": {"ino": path.stat().st_ino}, **{name: read(path / name)[1] for name in names}}
    def write(path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)
    for name, raw in {"token": b"synthetic-token\n", "label": b"deploy:backend\n",
                      "stage": (str(stage) + "\n").encode(), "started_at": b"2026-09-09T00:00:00Z\n"}.items():
        write(lease / name, raw)
    for name in ("staged.sha256", "backend.env.rollback", "backend.env.candidate", "script.py"):
        write(stage / name, b"synthetic sealed material\n")
    for name in ("started.json", "completed.json", "deployment.log", "preparation.log"):
        write(workspace / name, b"original failure evidence\n")
    for name in ("known_hosts", "loopback.conf", "authorized-release.json", "loopback.pub", "cloud.pub", "loopback.key"):
        write(config / name, (name + " value\n").encode())
    write(config / "authorized-release.json", json.dumps({"expires_at": 100}).encode())
    write(config / "cloud.pub", b"ssh-ed25519 cloud\n")
    write(config / "loopback.pub", b"ssh-ed25519 loopback\n")
    installed = library / "trusted_release_server.py"
    write(installed, b"canonical executor")
    authorized = tmp_path / "authorized"
    write(authorized, b"unrelated\ncloud exact\nloopback exact\n")
    for path in (state / "launcher.lock", workspace / "build.lock"):
        write(path, b"")
    services = {"stable": "running"}
    snapshot = {"workspace": {"inventory": sorted(p.name for p in workspace.iterdir())},
                "stage": {"lease": {}, **{n: read(lease / n)[1] for n in ("token", "label", "stage", "started_at")},
                          "manifest": read(stage / "staged.sha256")[1],
                          **{n: read(stage / n)[1] for n in ("backend.env.rollback", "backend.env.candidate", "script.py")}}}
    restore_intent = {"recovery_sha": restored_sha, "failed_sha": old, "production_sha": production, "snapshot": snapshot}
    restore_intent["evidence_sha256"] = m._digest(restore_intent)
    restore_completed = {k: v for k, v in restore_intent.items() if k != "snapshot"}
    restore_completed.update(state="RESTORED_PREVIOUS_SERVICES", stable_services=services,
                             original_release_and_lease_preserved=True)
    audit = state / "contained-service-recoveries" / old
    audit.mkdir(parents=True, mode=0o700)
    write(audit / "intent.json", json.dumps(restore_intent).encode())
    write(audit / "completed.json", json.dumps(restore_completed).encode())
    b = SimpleNamespace(STATE=state, CONFIG=config, INSTALLED=installed, AUTHORIZED=authorized,
        secure=lambda *a, **k: None, _inventory=inventory,
        _read_json=lambda p: json.loads(p.read_bytes()), canonical_source=lambda sha: tmp_path,
        _retired_history=lambda: {}, _assert_known_activity=lambda *a: None,
        _archives=lambda sha: (tmp_path / "old-config", tmp_path / "old-library"),
        validate_install=lambda *a, **k: None, key_lines=lambda *a: ("cloud exact", "loopback exact"),
        _recovery_process_proof=lambda: None, _assert_idle=lambda: None,
        _replace_authorized=lambda raw: write(authorized, raw),
        _recovery_file_identity=lambda path: read(path)[1])
    b._installation_evidence = lambda *a: {"config": inventory(config, {p.name for p in config.iterdir()}),
                                         "library": inventory(library, {installed.name})}
    p = SimpleNamespace(failed_sha=old, production_sha=production, lease=lease, stage=stage,
        snapshot=lambda: snapshot, _file=read, running_snapshot=lambda: services,
        running_services_snapshot=lambda: services)
    r = SimpleNamespace(_wait_ready=lambda p: p.running_snapshot(), _http_probes=lambda: None,
                        _application_probes=lambda *a: None)
    adapter = m.ClosureAdapter(p, b, r, closing, lambda: None)
    # Metadata/alias validation is separately tested in RecoveryProof; here
    # assert the real rename retains inode and bytes on an unprivileged OS.
    original_inode = lease.stat().st_ino
    def verify_archive(evidence):
        assert not lease.exists()
        assert adapter.volatile.stat().st_ino == original_inode
        for name, identity in m._expected_archives(snapshot)["lease"].items():
            assert read(adapter.volatile / name)[1] == identity
    monkeypatch.setattr(adapter, "_verify_original_lease_archive", verify_archive)
    monkeypatch.setattr(m, "_workspace_unchanged", lambda *a: None)
    return m, adapter, b, r, audit


def test_real_archival_revokes_only_managed_keys_preserves_failure_and_allows_history(tmp_path, monkeypatch):
    m, a, b, r, audit = proof_fixture(tmp_path, monkeypatch)
    original = (b.STATE / a.proof.failed_sha / "completed.json").read_bytes()
    digest = m.close_transaction(a)["evidence_sha256"]
    result = m.close_transaction(a, digest)
    assert b.AUTHORIZED.read_bytes() == b"unrelated\n"
    assert not (b.CONFIG / "loopback.key").exists()
    assert not a.proof.lease.exists()
    assert (b.STATE / a.proof.failed_sha / "completed.json").read_bytes() == original
    assert m.closed_evidence(b, a.proof.failed_sha, result["receipt"])["state"] == "CLOSED_RESTORED_RELEASE"
    with pytest.raises(m.ClosureError):
        m.closed_evidence(b, a.proof.failed_sha, None)
    (a.record / "lease/token").write_bytes(b"drift")
    with pytest.raises(m.ClosureError):
        m.closed_evidence(b, a.proof.failed_sha, result["receipt"])


@pytest.mark.parametrize("fault", ["recovery_missing", "recovery_false", "recovery_drift", "runtime", "auth", "process", "snapshot", "archive_exists", "application", "locks"])
def test_inspection_faults_never_revoke_or_archive(tmp_path, monkeypatch, fault):
    m, a, b, r, audit = proof_fixture(tmp_path, monkeypatch)
    auth = b.AUTHORIZED.read_bytes()
    if fault == "recovery_missing":
        (audit / "completed.json").unlink()
    elif fault in {"recovery_false", "recovery_drift"}:
        data = json.loads((audit / "completed.json").read_text())
        data["original_release_and_lease_preserved"] = 1 if fault == "recovery_false" else False
        (audit / "completed.json").write_text(json.dumps(data))
    elif fault == "runtime":
        r._wait_ready = lambda p: {"unstable": True}
    elif fault == "auth":
        b.AUTHORIZED.write_bytes(auth + b"cloud exact\n")
        auth = b.AUTHORIZED.read_bytes()
    elif fault == "snapshot":
        a.proof.snapshot()["changed"] = True
    elif fault == "archive_exists":
        a.volatile.mkdir()
    else:
        def fail(*args):
            raise m.ClosureError("injected rejection")
        if fault == "process":
            b._recovery_process_proof = fail
        elif fault == "application":
            r._application_probes = fail
        else:
            a.check = fail
    with pytest.raises((m.ClosureError, FileNotFoundError)):
        m.close_transaction(a)
    assert b.AUTHORIZED.read_bytes() == auth
    assert (b.CONFIG / "loopback.key").exists()
    assert a.proof.lease.exists()
    assert not a.record.exists()


@pytest.mark.parametrize("target", ["receipt", "completed", "intent", "restoration", "stage", "installation", "launcher"])
def test_closed_history_rejects_changed_or_incomplete_evidence(tmp_path, monkeypatch, target):
    m, a, b, r, audit = proof_fixture(tmp_path, monkeypatch)
    result = m.close_transaction(a, m.close_transaction(a)["evidence_sha256"])
    receipt = result["receipt"]
    if target == "receipt":
        receipt = "f" * 64
    elif target == "completed":
        (a.record / "completed.json").unlink()
    elif target == "intent":
        data = json.loads((a.record / "intent.json").read_text())
        data["production_sha"] = "f" * 40
        (a.record / "intent.json").write_text(json.dumps(data))
    elif target == "restoration":
        (audit / "completed.json").write_text("{}")
    elif target == "stage":
        (a.record / "stage/script.py").write_bytes(b"changed")
    elif target == "installation":
        (b.CONFIG / "loopback.key").write_bytes(b"unexpected key")
    else:
        (b.STATE / "launcher.lock").write_bytes(b"changed lock")
    with pytest.raises((m.ClosureError, FileNotFoundError)):
        m.closed_evidence(b, a.proof.failed_sha, receipt)


def test_native_lease_move_never_overwrites_a_racing_target(monkeypatch):
    m = load()
    calls = []
    monkeypatch.setattr(m.subprocess, "run", lambda argv, **kwargs: calls.append((argv, kwargs)))
    m._move_no_clobber(Path("/run/lock/source"), Path("/run/lock/target"))
    assert calls[0][0] == ["/usr/bin/mv", "--no-clobber", "-T", "--", "/run/lock/source", "/run/lock/target"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == 15


def test_partial_closure_blocks_bootstrap_instead_of_using_old_failure_marker(tmp_path, monkeypatch):
    import sys
    spec = importlib.util.spec_from_file_location("closure_bootstrap_test", Path(__file__).with_name("bootstrap_trusted_release.py"))
    b = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, b)
    spec.loader.exec_module(b)
    b.STATE = tmp_path
    old = "a" * 40
    (tmp_path / "contained-release-closures" / old).mkdir(parents=True, mode=0o700)
    # Canonical metadata checks are exercised separately; no real privileged files.
    b.secure = lambda *a, **k: None
    source = tmp_path / "canonical"
    source.mkdir()
    import shutil
    shutil.copyfile(Path(__file__).with_name("contained_release_retirement.py"), source / "contained_release_retirement.py")
    b.__file__ = str(source / "bootstrap_trusted_release.py")
    with pytest.raises(Exception, match="private closure directory|closure audit incomplete"):
        b._workspace_evidence(old, recovery_receipt="c" * 64)
