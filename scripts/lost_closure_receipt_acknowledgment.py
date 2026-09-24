"""One-time audited acknowledgment for a completed closure whose secret was lost.

This module never reconstructs or changes the original closure receipt. It
binds a new explicit administrative decision to the still-valid immutable
closure, stable production revision, revoked identities, and an idle release
host. It is loaded only by the canonical isolated bootstrap operator.
"""

import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
from pathlib import Path


ROOT_NAME = "lost-closure-receipt-acknowledgments"


class AcknowledgmentError(Exception):
    """Static, secret-free operator failure."""


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path, value):
    raw = json.dumps(value, sort_keys=True).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync(path.parent)


def _load_closure(bootstrap):
    path = Path(bootstrap.__file__).absolute().with_name("contained_release_retirement.py")
    bootstrap.secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise AcknowledgmentError("cached closure proof forbidden")
    spec = importlib.util.spec_from_file_location("acknowledged_completed_closure", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(bootstrap, old_sha):
    return bootstrap.STATE / ROOT_NAME / old_sha


def _private_directory(bootstrap, path):
    bootstrap.secure(path)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise AcknowledgmentError("private root-owned acknowledgment directory required")


def _inspect(bootstrap, old_sha, acknowledging_sha, check_locks):
    check_locks()
    if (not isinstance(old_sha, str) or re.fullmatch(r"[0-9a-f]{40}", old_sha) is None
            or not isinstance(acknowledging_sha, str) or re.fullmatch(r"[0-9a-f]{40}", acknowledging_sha) is None
            or old_sha == acknowledging_sha):
        raise AcknowledgmentError("distinct exact closure and acknowledgment SHAs required")
    source = bootstrap.canonical_source(acknowledging_sha)
    closure = _load_closure(bootstrap).closure_evidence_without_receipt(
        bootstrap, old_sha, unchanged=True)
    if closure.get("state") != "CLOSED_UNCHANGED_RELEASE":
        raise AcknowledgmentError("only a completed unchanged closure can be acknowledged")
    bootstrap._assert_idle()
    bootstrap._recovery_process_proof()
    if os.path.lexists(bootstrap.BUSINESS_LEASE):
        raise AcknowledgmentError("business release lease exists")
    bootstrap._recovery_production_proof(closure["production_sha"], source)
    authorized = bootstrap._recovery_file_identity(bootstrap.AUTHORIZED)
    bootstrap._assert_idle()
    bootstrap._recovery_process_proof()
    if os.path.lexists(bootstrap.BUSINESS_LEASE):
        raise AcknowledgmentError("business release lease appeared")
    check_locks()
    return {
        "old_sha": old_sha,
        "acknowledging_sha": acknowledging_sha,
        "production_sha": closure["production_sha"],
        "closure": closure,
        "authorized": authorized,
    }


def acknowledge(bootstrap, old_sha, acknowledging_sha, check_locks, *, evidence_sha256=None, accepted=False):
    check_locks()
    record = _record(bootstrap, old_sha)
    if os.path.lexists(record):
        raise AcknowledgmentError("lost receipt acknowledgment already attempted; retry forbidden")
    if os.path.lexists(record.parent):
        _private_directory(bootstrap, record.parent)
    else:
        _private_directory(bootstrap, record.parent.parent)
    evidence = _inspect(bootstrap, old_sha, acknowledging_sha, check_locks)
    digest = _digest(evidence)
    if evidence_sha256 is None:
        return {"state": "INSPECTED_LOST_CLOSURE_RECEIPT", "evidence_sha256": digest}
    if not accepted:
        raise AcknowledgmentError("explicit acceptance of the lost closure receipt is required")
    if evidence_sha256 != digest:
        raise AcknowledgmentError("lost receipt evidence changed")
    if not record.parent.exists():
        record.parent.mkdir(mode=0o700)
        _sync(record.parent.parent)
        _private_directory(bootstrap, record.parent)
    record.mkdir(mode=0o700)
    _sync(record.parent)
    _private_directory(bootstrap, record)
    receipt = secrets.token_hex(32)
    intent = {
        **evidence,
        "evidence_sha256": digest,
        "accepted_lost_closure_receipt": True,
        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
    }
    check_locks()
    _write(record / "intent.json", intent)
    if _inspect(bootstrap, old_sha, acknowledging_sha, check_locks) != evidence:
        raise AcknowledgmentError("lost receipt evidence drift after intent")
    check_locks()
    _write(record / "completed.json", {
        "old_sha": old_sha,
        "acknowledging_sha": acknowledging_sha,
        "state": "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT",
        "intent_sha256": _digest(intent),
    })
    return {"sha": old_sha, "state": "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT", "receipt": receipt}


def acknowledged_evidence(bootstrap, old_sha, receipt, *, historical=False):
    record = _record(bootstrap, old_sha)
    _private_directory(bootstrap, record.parent)
    _private_directory(bootstrap, record)
    if not record.is_dir() or {p.name for p in record.iterdir()} != {"intent.json", "completed.json"}:
        raise AcknowledgmentError("lost receipt acknowledgment audit incomplete")
    for name in ("intent.json", "completed.json"):
        bootstrap.secure(record / name, private=True)
    intent = bootstrap._read_json(record / "intent.json")
    completed = bootstrap._read_json(record / "completed.json")
    expected_intent = {
        "old_sha", "acknowledging_sha", "production_sha", "closure", "authorized",
        "evidence_sha256", "accepted_lost_closure_receipt", "receipt_sha256",
    }
    if (not isinstance(intent, dict) or set(intent) != expected_intent
            or intent.get("old_sha") != old_sha
            or intent.get("accepted_lost_closure_receipt") is not True
            or intent.get("evidence_sha256") != _digest({
                key: value for key, value in intent.items()
                if key not in {"evidence_sha256", "accepted_lost_closure_receipt", "receipt_sha256"}
            })
            or completed != {
                "old_sha": old_sha,
                "acknowledging_sha": intent.get("acknowledging_sha"),
                "state": "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT",
                "intent_sha256": _digest(intent),
            }):
        raise AcknowledgmentError("lost receipt acknowledgment binding invalid")
    if (not isinstance(receipt, str) or re.fullmatch(r"[0-9a-f]{64}", receipt) is None
            or not isinstance(intent.get("receipt_sha256"), str)
            or not secrets.compare_digest(hashlib.sha256(receipt.encode()).hexdigest(), intent["receipt_sha256"])):
        raise AcknowledgmentError("durably issued acknowledgment receipt required")
    closure = _load_closure(bootstrap).closure_evidence_without_receipt(
        bootstrap, old_sha, unchanged=True)
    bootstrap.canonical_source(intent["acknowledging_sha"])
    if closure != intent["closure"] or closure["production_sha"] != intent["production_sha"]:
        raise AcknowledgmentError("acknowledged closure evidence changed")
    if not historical:
        evidence = _inspect(bootstrap, old_sha, intent["acknowledging_sha"], lambda: None)
        if evidence != {key: intent[key] for key in evidence}:
            raise AcknowledgmentError("acknowledged live evidence changed before consumption")
    return {
        "state": "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT",
        "closure": intent["closure"]["closure"],
        "acknowledgment": _digest(completed),
        "workspace": intent["closure"]["workspace"],
    }
