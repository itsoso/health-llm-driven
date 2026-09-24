"""Offline contract tests for the lost closure receipt acknowledgment."""

import importlib.util
import hashlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest


OLD = "a" * 40
ACK = "b" * 40
PRODUCTION = "c" * 40


def load():
    path = Path(__file__).with_name("lost_closure_receipt_acknowledgment.py")
    spec = importlib.util.spec_from_file_location("lost_closure_receipt_ack_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path, monkeypatch):
    module = load()
    state = tmp_path / "state"
    state.mkdir(mode=0o755)
    closure = state / "unchanged-release-closures" / OLD
    closure.mkdir(parents=True)
    bootstrap = SimpleNamespace(
        STATE=state,
        AUTHORIZED=tmp_path / "authorized_keys",
        BUSINESS_LEASE=tmp_path / "business-lease",
        secure=lambda *args, **kwargs: None,
        canonical_source=lambda sha: tmp_path / "canonical",
        _recovery_production_proof=lambda sha, source: None,
        _assert_idle=lambda: None,
        _recovery_process_proof=lambda: None,
        _read_json=lambda path: json.loads(path.read_text()),
        _recovery_file_identity=lambda path: {
            "inode": 1,
            "device": 2,
            "uid": 0,
            "gid": 0,
            "mode": 0o600,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    )
    bootstrap.AUTHORIZED.write_text("unrelated key\n")
    closure_module = SimpleNamespace(
        closure_evidence_without_receipt=lambda b, sha, unchanged: {
            "state": "CLOSED_UNCHANGED_RELEASE",
            "closure": "e" * 64,
            "workspace": {"inventory": []},
            "production_sha": PRODUCTION,
        }
    )
    monkeypatch.setattr(module, "_load_closure", lambda b: closure_module)
    def private_directory(_bootstrap, path):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
            raise module.AcknowledgmentError("private root-owned acknowledgment directory required")
    monkeypatch.setattr(module, "_private_directory", private_directory)
    monkeypatch.setattr(module, "_secure_root_directory", lambda _bootstrap, path: None)
    return module, bootstrap


def test_inspection_is_read_only_and_requires_explicit_acceptance(tmp_path, monkeypatch):
    module, bootstrap = fixture(tmp_path, monkeypatch)
    inspected = module.acknowledge(bootstrap, OLD, ACK, lambda: None)
    assert inspected["state"] == "INSPECTED_LOST_CLOSURE_RECEIPT"
    assert not (bootstrap.STATE / module.ROOT_NAME / OLD).exists()
    with pytest.raises(module.AcknowledgmentError, match="explicit acceptance"):
        module.acknowledge(
            bootstrap,
            OLD,
            ACK,
            lambda: None,
            evidence_sha256=inspected["evidence_sha256"],
            accepted=False,
        )


def test_acknowledgment_is_durable_one_time_and_receipt_is_not_persisted(tmp_path, monkeypatch):
    module, bootstrap = fixture(tmp_path, monkeypatch)
    inspected = module.acknowledge(bootstrap, OLD, ACK, lambda: None)
    result = module.acknowledge(
        bootstrap,
        OLD,
        ACK,
        lambda: None,
        evidence_sha256=inspected["evidence_sha256"],
        accepted=True,
    )
    record = bootstrap.STATE / module.ROOT_NAME / OLD
    intent = json.loads((record / "intent.json").read_text())
    assert result["state"] == "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT"
    assert len(result["receipt"]) == 64
    assert result["receipt"] not in (record / "intent.json").read_text()
    assert module.acknowledged_evidence(bootstrap, OLD, result["receipt"])["state"] == result["state"]
    with pytest.raises(module.AcknowledgmentError):
        module.acknowledge(bootstrap, OLD, ACK, lambda: None)
    with pytest.raises(module.AcknowledgmentError, match="receipt"):
        module.acknowledged_evidence(bootstrap, OLD, "f" * 64)
    assert intent["receipt_sha256"] == module.hashlib.sha256(result["receipt"].encode()).hexdigest()


@pytest.mark.parametrize("fault", ["closure", "production", "idle", "process", "authorization"])
def test_drift_or_active_release_blocks_before_record_creation(tmp_path, monkeypatch, fault):
    module, bootstrap = fixture(tmp_path, monkeypatch)
    inspected = module.acknowledge(bootstrap, OLD, ACK, lambda: None)
    if fault == "closure":
        monkeypatch.setattr(module, "_load_closure", lambda b: SimpleNamespace(
            closure_evidence_without_receipt=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("drift"))))
    elif fault == "production":
        bootstrap._recovery_production_proof = lambda *args: (_ for _ in ()).throw(RuntimeError("drift"))
    elif fault == "idle":
        bootstrap._assert_idle = lambda: (_ for _ in ()).throw(RuntimeError("active"))
    elif fault == "process":
        bootstrap._recovery_process_proof = lambda: (_ for _ in ()).throw(RuntimeError("active"))
    else:
        bootstrap.AUTHORIZED.write_text("changed\n")
    with pytest.raises((module.AcknowledgmentError, RuntimeError)):
        module.acknowledge(
            bootstrap,
            OLD,
            ACK,
            lambda: None,
            evidence_sha256=inspected["evidence_sha256"],
            accepted=True,
        )
    assert not (bootstrap.STATE / module.ROOT_NAME / OLD).exists()


def test_partial_or_modified_acknowledgment_cannot_authorize_rotation(tmp_path, monkeypatch):
    module, bootstrap = fixture(tmp_path, monkeypatch)
    inspected = module.acknowledge(bootstrap, OLD, ACK, lambda: None)
    result = module.acknowledge(
        bootstrap, OLD, ACK, lambda: None, evidence_sha256=inspected["evidence_sha256"], accepted=True)
    record = bootstrap.STATE / module.ROOT_NAME / OLD
    (record / "completed.json").unlink()
    with pytest.raises(module.AcknowledgmentError, match="incomplete"):
        module.acknowledged_evidence(bootstrap, OLD, result["receipt"])


def test_failure_after_intent_is_durable_and_never_retries(tmp_path, monkeypatch):
    module, bootstrap = fixture(tmp_path, monkeypatch)
    inspected = module.acknowledge(bootstrap, OLD, ACK, lambda: None)
    original_write = module._write

    def fail_completion(path, value):
        if path.name == "completed.json":
            raise OSError("injected completion failure")
        original_write(path, value)

    monkeypatch.setattr(module, "_write", fail_completion)
    with pytest.raises(OSError):
        module.acknowledge(
            bootstrap, OLD, ACK, lambda: None,
            evidence_sha256=inspected["evidence_sha256"], accepted=True)
    record = bootstrap.STATE / module.ROOT_NAME / OLD
    assert (record / "intent.json").is_file()
    assert not (record / "completed.json").exists()
    with pytest.raises(module.AcknowledgmentError, match="already attempted"):
        module.acknowledge(bootstrap, OLD, ACK, lambda: None)


def test_historical_verification_does_not_depend_on_future_live_state(tmp_path, monkeypatch):
    module, bootstrap = fixture(tmp_path, monkeypatch)
    inspected = module.acknowledge(bootstrap, OLD, ACK, lambda: None)
    result = module.acknowledge(
        bootstrap, OLD, ACK, lambda: None, evidence_sha256=inspected["evidence_sha256"], accepted=True)
    bootstrap.AUTHORIZED.write_text("new release identity\n")
    bootstrap._assert_idle = lambda: (_ for _ in ()).throw(RuntimeError("active future release"))
    bootstrap._recovery_production_proof = lambda *args: (_ for _ in ()).throw(RuntimeError("new production"))
    assert module.acknowledged_evidence(
        bootstrap, OLD, result["receipt"], historical=True)["state"] == "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT"
    with pytest.raises(RuntimeError):
        module.acknowledged_evidence(bootstrap, OLD, result["receipt"])


@pytest.mark.parametrize("kind", ["world_writable", "symlink"])
def test_unsafe_audit_parent_is_rejected_before_any_record_write(tmp_path, monkeypatch, kind):
    module, bootstrap = fixture(tmp_path, monkeypatch)
    parent = bootstrap.STATE / module.ROOT_NAME
    if kind == "world_writable":
        parent.mkdir(mode=0o700)
        parent.chmod(0o777)
    else:
        outside = tmp_path / "outside"
        outside.mkdir(mode=0o700)
        parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(module.AcknowledgmentError, match="private root-owned"):
        module.acknowledge(bootstrap, OLD, ACK, lambda: None)
    assert not (parent / OLD).exists()


def test_real_directory_guard_calls_bootstrap_security_and_rejects_world_writable(tmp_path):
    module = load()
    path = tmp_path / "audit"
    path.mkdir(mode=0o700)
    path.chmod(0o777)
    calls = []
    bootstrap = SimpleNamespace(secure=lambda value: calls.append(value))
    with pytest.raises(module.AcknowledgmentError, match="private root-owned"):
        module._private_directory(bootstrap, path)
    assert calls == [path]


def test_acknowledgment_parent_accepts_secure_root_owned_0755_state(monkeypatch):
    module = load()
    info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0, st_gid=0)
    path = SimpleNamespace(lstat=lambda: info)
    calls = []
    module._secure_root_directory(SimpleNamespace(secure=lambda value: calls.append(value)), path)
    assert calls == [path]


def test_lock_identity_is_rechecked_around_inspection_and_durable_writes(tmp_path, monkeypatch):
    module, bootstrap = fixture(tmp_path, monkeypatch)
    checks = []
    def check_locks():
        checks.append(len(checks) + 1)
    inspected = module.acknowledge(bootstrap, OLD, ACK, check_locks)
    inspection_checks = len(checks)
    module.acknowledge(
        bootstrap, OLD, ACK, check_locks,
        evidence_sha256=inspected["evidence_sha256"], accepted=True)
    assert inspection_checks >= 3
    assert len(checks) >= inspection_checks + 6
