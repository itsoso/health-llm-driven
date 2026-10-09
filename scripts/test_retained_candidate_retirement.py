"""Failure closure archives facts; it cannot turn a failed release into success."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    spec = importlib.util.spec_from_file_location(
        "retained_test", Path(__file__).with_name("retained_candidate_retirement.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def marker(candidate="b" * 40):
    old = "a" * 40
    transaction = hashlib.sha256(f"{old}:{candidate}".encode()).hexdigest()[:32]
    return {
        "version": 1,
        "old_sha": old,
        "candidate_sha": candidate,
        "terminal_sha": candidate,
        "phase": "COMMITTED",
        "target": "candidate",
        "result": "finalized",
        "transaction_id": transaction,
        "reap_name": "runtime-state-transaction.reap-" + transaction,
    }


def test_terminal_requires_exact_finalized_candidate():
    m = load()
    m.validate_terminal(marker(), "b" * 40)
    for field, value in [
        ("version", True),
        ("phase", "RESTORE_FINALIZED"),
        ("target", "old"),
        ("result", "unknown"),
        ("terminal_sha", "a" * 40),
        ("candidate_sha", "c" * 40),
        ("transaction_id", "0" * 32),
        ("extra", 1),
    ]:
        altered = marker()
        altered[field] = value
        with pytest.raises(m.RetirementError):
            m.validate_terminal(altered, "b" * 40)


class Adapter:
    def __init__(self, path):
        self.record = path / "retained" / ("b" * 40)
        self.value = {
            "old_sha": "b" * 40,
            "closing_sha": "c" * 40,
            "terminal": marker(),
        }
        self.calls = 0
        self.drift = False

    def check_record_parent(self):
        pass

    def inspect(self):
        self.calls += 1
        value = copy.deepcopy(self.value)
        if self.drift and self.calls > 1:
            value["closing_sha"] = "d" * 40
        return value


def test_inspect_is_read_only_and_close_issues_receipt_only_after_completion(tmp_path):
    m = load()
    a = Adapter(tmp_path)
    inspected = m.close_transaction(a)
    assert not a.record.exists()
    result = m.close_transaction(a, inspected["evidence_sha256"])
    assert result["state"] == "CLOSED_RETAINED_CANDIDATE_FAILURE"
    assert {p.name for p in a.record.iterdir()} == {"intent.json", "completed.json"}
    intent = json.loads((a.record / "intent.json").read_text())
    assert (
        hashlib.sha256(result["receipt"].encode()).hexdigest()
        == intent["receipt_sha256"]
    )
    assert result["receipt"] not in (a.record / "intent.json").read_text()
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, inspected["evidence_sha256"])


def test_stale_digest_never_consumes_and_post_intent_drift_stays_blocked(tmp_path):
    m = load()
    a = Adapter(tmp_path)
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, "0" * 64)
    assert not a.record.exists()
    a.calls = 0
    a.drift = True
    digest = m.digest(a.value)
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, digest)
    assert (a.record / "intent.json").exists()
    assert not (a.record / "completed.json").exists()
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, digest)


def test_pending_transaction_blocks_even_with_valid_terminal(tmp_path):
    m = load()
    (tmp_path / "runtime-state-transaction.reap-dead").mkdir()
    with pytest.raises(m.RetirementError):
        m.assert_no_transaction(tmp_path)


def test_no_finalization_or_success_receipt_written():
    m = load()
    text = Path(m.__file__).read_text()
    assert ".finalize(" not in text and ".commit(" not in text
    assert '"SUCCEEDED"' not in text


def history_fixture(monkeypatch, tmp_path):
    m = load()
    sha = "b" * 40
    closing = "c" * 40
    receipt = "d" * 64
    root = tmp_path / m.ROOT_NAME / sha
    root.mkdir(parents=True)
    live = {
        "terminal": marker(),
        "terminal_identity": {
            "uid": 0,
            "gid": 0,
            "mode": 0o600,
            "inode": 1,
            "device": 1,
            "sha256": "e" * 64,
        },
        "services": {},
        "probes": {
            "schema": True,
            "runtime_only_kb": True,
            "auth_unauthenticated_401": True,
            "health_dependencies": True,
            "runtime_flag_false": True,
        },
    }
    # Live services are validated by the canonical service proof; history holds
    # that immutable snapshot instead of querying a different deployment.
    for unit in (
        "health-backend.socket",
        "health-backend.service",
        "celery-worker.service",
        "celery-beat.service",
    ):
        live["services"][unit] = {
            "ActiveState": "active",
            "SubState": "listening" if unit.endswith(".socket") else "running",
            "MainPID": "0" if unit.endswith(".socket") else "123",
            "NRestarts": "0",
            "ActiveEnterTimestampMonotonic": "123",
            "ControlGroup": "/system.slice/" + unit,
            "Result": "success",
        }
        if unit.endswith(".service"):
            live["services"][unit]["processes"] = {"123": "789"}
    evidence = {
        "old_sha": sha,
        "closing_sha": closing,
        "workspace": {"manifest": "old"},
        "installation": {"old": "installation"},
        "live": live,
        "launcher": {"old": "lock"},
    }
    intent = {
        **evidence,
        "evidence_sha256": m.digest(evidence),
        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
    }
    completed = {"state": m.TERMINAL, "old_sha": sha, "intent_sha256": m.digest(intent)}
    for name, value in [("intent.json", intent), ("completed.json", completed)]:
        (root / name).write_text(json.dumps(value))
    b = SimpleNamespace(
        STATE=tmp_path,
        CONFIG=tmp_path / "config",
        INSTALLED=tmp_path / "lib" / "server.py",
        secure=lambda *a, **k: None,
        _inventory=lambda *a: None,
        _read_json=lambda p: json.loads(p.read_text()),
        canonical_source=lambda sha: tmp_path / "source",
        _archives=lambda sha: (tmp_path / "archconfig", tmp_path / "archlib"),
        _installation_evidence=lambda *a: evidence["installation"],
        _recovery_file_identity=lambda p: evidence["launcher"],
    )
    monkeypatch.setattr(m, "private_directory", lambda *a: None)
    monkeypatch.setattr(m, "workspace_evidence", lambda *a: evidence["workspace"])
    return m, b, sha, receipt, evidence


def test_history_never_queries_future_production(monkeypatch, tmp_path):
    m, b, sha, receipt, _evidence = history_fixture(monkeypatch, tmp_path)

    def forbidden(*a):
        raise AssertionError("history must not inspect current production")

    monkeypatch.setattr(m, "live_state", forbidden)
    assert m.closed_evidence(b, sha, receipt, historical=True)["state"] == m.TERMINAL
    with pytest.raises(AssertionError):
        m.closed_evidence(b, sha, receipt, historical=False)
    with pytest.raises(m.RetirementError):
        m.closed_evidence(b, sha, "f" * 64, historical=True)
    monkeypatch.setattr(m, "workspace_evidence", lambda *a: {"manifest": "changed"})
    with pytest.raises(m.RetirementError):
        m.closed_evidence(b, sha, receipt, historical=True)


@pytest.mark.parametrize("fault", ["terminal", "probe", "service", "identity"])
def test_self_consistent_but_invalid_archived_proof_is_rejected(
    monkeypatch, tmp_path, fault
):
    m, b, sha, receipt, evidence = history_fixture(monkeypatch, tmp_path)
    if fault == "terminal":
        evidence["live"]["terminal"]["phase"] = "RESTORE_FINALIZED"
    if fault == "probe":
        evidence["live"]["probes"]["schema"] = False
    if fault == "service":
        evidence["live"]["services"]["celery-worker.service"]["Result"] = "failed"
    if fault == "identity":
        evidence["live"]["terminal_identity"]["uid"] = 1000
    intent = {
        **evidence,
        "evidence_sha256": m.digest(evidence),
        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
    }
    root = tmp_path / m.ROOT_NAME / sha
    (root / "intent.json").write_text(json.dumps(intent))
    (root / "completed.json").write_text(
        json.dumps(
            {"state": m.TERMINAL, "old_sha": sha, "intent_sha256": m.digest(intent)}
        )
    )
    with pytest.raises(m.RetirementError):
        m.closed_evidence(b, sha, receipt, historical=True)


def workspace_fixture(monkeypatch, tmp_path):
    m = load()
    sha = "b" * 40
    root = tmp_path / sha
    root.mkdir()
    source = tmp_path / "canonical"
    (source / "scripts").mkdir(parents=True)
    executor = source / "scripts/trusted_release_server.py"
    executor.write_text("# canonical executor\n")
    for name, state in [
        ("started.json", "STARTED"),
        ("preparation-started.json", "PREPARING"),
        ("prepared.json", "PREPARED"),
        ("deployment-started.json", "DEPLOYING"),
        ("completed.json", "NEEDS_OPERATOR"),
    ]:
        value = {"sha": sha, "state": state}
        if name == "preparation-started.json":
            value["executor_sha256"] = hashlib.sha256(executor.read_bytes()).hexdigest()
        (root / name).write_text(json.dumps(value))
    for name in ("preparation.log", "deployment.log", "deployment.env"):
        (root / name).write_text("private bytes")
    for name in ("source", "home", "bin"):
        (root / name).mkdir()
    spec = importlib.util.spec_from_file_location(
        "retained_manifest", Path(__file__).with_name("bootstrap_trusted_release.py")
    )
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    monkeypatch.setattr(b, "secure", lambda *a, **k: None)
    b.STATE = tmp_path
    monkeypatch.setattr(b, "canonical_source", lambda sha: source)
    monkeypatch.setattr(m, "private_directory", lambda *a: None)
    return m, b, sha, root


def test_workspace_keeps_original_failure_and_detects_every_retained_byte(
    monkeypatch, tmp_path
):
    m, b, sha, root = workspace_fixture(monkeypatch, tmp_path)
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    proof = m.workspace_evidence(b, sha)
    assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    (root / "source" / "retained").write_text("additional private content")
    assert m.workspace_evidence(b, sha) != proof
    (root / "source" / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(b.BootstrapError):
        m.workspace_evidence(b, sha)


@pytest.mark.parametrize(
    "fault", ["claim", "extra", "incomplete", "wrong_sha", "executor"]
)
def test_workspace_rejects_mixed_claim_and_invalid_phase(monkeypatch, tmp_path, fault):
    m, b, sha, root = workspace_fixture(monkeypatch, tmp_path)
    if fault == "claim":
        (root / "build.lock").touch()
    if fault == "extra":
        (root / "unexpected").touch()
    if fault == "incomplete":
        (root / "prepared.json").unlink()
    if fault == "wrong_sha":
        (root / "completed.json").write_text(
            json.dumps({"sha": "a" * 40, "state": "NEEDS_OPERATOR"})
        )
    if fault == "executor":
        (root / "preparation-started.json").write_text(
            json.dumps({"sha": sha, "state": "PREPARING", "executor_sha256": "f" * 64})
        )
    with pytest.raises(m.RetirementError):
        m.workspace_evidence(b, sha)


def test_completion_write_failure_never_returns_receipt_or_retries(
    monkeypatch, tmp_path
):
    m = load()
    a = Adapter(tmp_path)
    original = m.write_json

    def fail(path, value):
        if path.name == "completed.json":
            raise OSError("injected durability fault")
        original(path, value)

    monkeypatch.setattr(m, "write_json", fail)
    with pytest.raises(OSError):
        m.close_transaction(a, m.digest(a.value))
    assert (a.record / "intent.json").exists()
    assert not (a.record / "completed.json").exists()
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, m.digest(a.value))
