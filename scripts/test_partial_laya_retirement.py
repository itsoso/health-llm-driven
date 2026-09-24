"""Offline tests: never run a partial environment or touch production."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


def module():
    spec = importlib.util.spec_from_file_location("partial_laya", Path(__file__).with_name("partial_laya_retirement.py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_terminal_is_separate_from_success_or_unchanged():
    m = module()
    assert m.TERMINAL == "CLOSED_PARTIAL_LAYA_ORPHANED_LEASE"
    assert m.LEASE_STATE == "ABSENT_CAUSE_UNKNOWN"


def test_static_manifest_does_not_execute_python(tmp_path, monkeypatch):
    m = module()
    monkeypatch.setattr(m, "OWNER", os.getuid())
    monkeypatch.setattr(m, "GROUP", os.getgid())
    (tmp_path / "venv/bin").mkdir(parents=True)
    (tmp_path / "venv/bin/python3.12").symlink_to("/usr/bin/python3.12")
    (tmp_path / "data").write_bytes(b"opaque")
    first = m.tree_manifest(tmp_path)
    assert first == m.tree_manifest(tmp_path)
    (tmp_path / "data").write_bytes(b"changed")
    assert first != m.tree_manifest(tmp_path)


@pytest.mark.parametrize("damage", ["link", "hardlink", "fifo", "writable", "escape"])
def test_static_manifest_rejects_unsafe_objects(tmp_path, monkeypatch, damage):
    m = module()
    monkeypatch.setattr(m, "OWNER", os.getuid())
    monkeypatch.setattr(m, "GROUP", os.getgid())
    target = tmp_path / "object"
    if damage in {"link", "escape"}:
        target.symlink_to("/etc/passwd" if damage == "escape" else "missing")
    elif damage == "fifo":
        os.mkfifo(target)
    else:
        target.write_bytes(b"opaque")
        if damage == "hardlink":
            os.link(target, tmp_path / "second")
        else:
            target.chmod(0o666)
    with pytest.raises(m.RetirementError):
        m.tree_manifest(tmp_path)


def test_transaction_keeps_unknown_lease_and_never_retries(tmp_path):
    m = module()
    class Adapter:
        record = tmp_path / "operations" / m.FAILED
        def __init__(self):
            self.calls = []
        def inspect(self):
            return {"old_sha": m.FAILED, "lease_state": m.LEASE_STATE}
        def archive_and_revoke(self, evidence):
            self.calls.append("archive")
        def verify_closed(self, evidence):
            return {"preserved": True}
    a = Adapter()
    inspected = m.close_transaction(a)
    assert a.calls == [] and not a.record.exists()
    result = m.close_transaction(a, inspected["evidence_sha256"])
    assert result["state"] == m.TERMINAL
    assert len(result["receipt"]) == 64
    assert a.calls == ["archive"]
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, inspected["evidence_sha256"])


def test_drift_blocks_before_intent(tmp_path):
    m = module()
    class Adapter:
        record = tmp_path / "ops" / m.FAILED
        def inspect(self):
            return {"old_sha": m.FAILED, "lease_state": m.LEASE_STATE}
    with pytest.raises(m.RetirementError):
        m.close_transaction(Adapter(), "0" * 64)
    assert not Adapter.record.exists()


@pytest.mark.parametrize("phase", ["reinspect", "archive", "verify", "terminal_fsync"])
def test_interruption_consumes_attempt_and_never_returns_receipt(tmp_path, monkeypatch, phase):
    m = module()
    class Adapter:
        record = tmp_path / "ops" / m.FAILED
        count = 0
        def inspect(self):
            self.count += 1
            if phase == "reinspect" and self.count == 3:
                raise m.RetirementError("synthetic")
            return {"old_sha": m.FAILED, "lease_state": m.LEASE_STATE}
        def archive_and_revoke(self, evidence):
            if phase == "archive":
                raise m.RetirementError("synthetic")
        def verify_closed(self, evidence):
            if phase == "verify":
                raise m.RetirementError("synthetic")
            return {"preserved": True}
    a = Adapter()
    inspected = m.close_transaction(a)
    original = m.write
    def broken(path, value):
        original(path, value)
        if phase == "terminal_fsync" and path.name == "completed.json":
            raise OSError("synthetic lost acknowledgment")
    monkeypatch.setattr(m, "write", broken)
    with pytest.raises((m.RetirementError, OSError)):
        m.close_transaction(a, inspected["evidence_sha256"])
    assert (a.record / "intent.json").exists()
    assert "receipt" not in json.loads((a.record / "intent.json").read_text())
    with pytest.raises(m.RetirementError, match="already attempted"):
        m.close_transaction(a, inspected["evidence_sha256"])


@pytest.fixture
def partial(tmp_path, monkeypatch):
    m = module()
    monkeypatch.setattr(m, "OWNER", os.getuid())
    monkeypatch.setattr(m, "GROUP", os.getgid())
    monkeypatch.setattr(m, "LAYA", tmp_path / "state")
    monkeypatch.setattr(m, "BASE", tmp_path / "base")
    # Synthetic canonical source; tests exercise binding, not any host command.
    assets = ("install.py", "serve.py", "reva-laya.service.in")
    raw = {name: ("canonical:" + name + "@GENERATION@").encode() for name in assets}
    generation_id = hashlib.sha256(b"".join(name.encode() + b"\0" + raw[name] for name in assets)).hexdigest()
    monkeypatch.setattr(m, "GENERATION", generation_id)
    source = m.LAYA / "sources" / m.FAILED
    source.mkdir(parents=True)
    (source.parent / m.BASELINE).mkdir()
    (source.parent / m.PREDECESSOR).mkdir()
    canonical = tmp_path / "canonical"
    (canonical / "infra/laya").mkdir(parents=True)
    generation = m.BASE / "generations" / generation_id
    generation.mkdir(parents=True)
    (generation / "venv").mkdir()
    for name, content in raw.items():
        (source / name).write_bytes(content)
        (source / name).chmod(0o400)
        (canonical / "infra/laya" / name).write_bytes(content)
        (generation / name).write_bytes(content)
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in raw.items()}
    (source / "source.json").write_text(json.dumps({"sha": m.FAILED, "old_sha": m.PRODUCTION,
             "old_has_decisions": False, "files": hashes}))
    (source / "source.json").chmod(0o400)
    receipt = {"generation": generation_id, "unit_sha256": hashlib.sha256(raw["reva-laya.service.in"].replace(b"@GENERATION@", str(generation).encode())).hexdigest(),
               "env_sha256": "a" * 64, "lease": "b" * 64, "state": "PREPARING", "candidate_sha": m.FAILED}
    path = m.LAYA / "install.json"
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    def file(path, mode=None):
        info = path.lstat()
        if mode is not None and info.st_mode & 0o777 != mode:
            raise m.RetirementError("mode mismatch")
        content = path.read_bytes()
        return content, {"sha256": hashlib.sha256(content).hexdigest()}
    a = m.Adapter.__new__(m.Adapter)
    a.b = SimpleNamespace(secure=lambda p: None, canonical_source=lambda sha: canonical)
    a.p = SimpleNamespace(_file=file, _directory=lambda path: {"ino": path.lstat().st_ino})
    a.module = SimpleNamespace(LAYA_ASSETS=assets, object_json=json.loads)
    return m, a, source, generation, path


def test_partial_admission_is_static_and_bound_to_old_source(partial, monkeypatch):
    m, a, _source, _generation, path = partial
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **kw: pytest.fail("must never execute partial code"))
    assert a.partial()["receipt"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("damage", ["prepared", "activating", "installed", "wrong_candidate", "missing_lease_digest",
                                  "wrong_unit", "extra_receipt", "source_bytes", "source_binding", "generation_asset",
                                  "model_files", "unknown_source", "extra_state", "archive_exists", "missing_receipt"])
def test_partial_admission_rejects_other_phases_and_drift(partial, damage):
    m, a, source, generation, path = partial
    receipt = json.loads(path.read_text())
    if damage in {"prepared", "activating", "installed"}:
        receipt["state"] = damage.upper()
    elif damage == "wrong_candidate":
        receipt["candidate_sha"] = "d" * 40
    elif damage == "missing_lease_digest":
        receipt.pop("lease")
    elif damage == "wrong_unit":
        receipt["unit_sha256"] = "e" * 64
    elif damage == "extra_receipt":
        receipt["extra"] = True
    elif damage == "source_bytes":
        (source / "install.py").chmod(0o600)
        (source / "install.py").write_text("changed")
        (source / "install.py").chmod(0o400)
    elif damage == "source_binding":
        (source / "source.json").chmod(0o600)
        (source / "source.json").write_text("{}")
        (source / "source.json").chmod(0o400)
    elif damage == "generation_asset":
        (generation / "install.py").write_text("changed")
    elif damage == "model_files":
        (generation / "models").mkdir()
    elif damage == "unknown_source":
        (source.parent / ("d" * 40)).mkdir()
    elif damage == "extra_state":
        (m.LAYA / "other").mkdir()
    elif damage == "archive_exists":
        m.archive_paths()[0].parent.parent.mkdir()
    elif damage == "missing_receipt":
        path.unlink()
    if path.exists():
        path.write_text(json.dumps(receipt))
    with pytest.raises((m.RetirementError, FileNotFoundError)):
        a.partial()


@pytest.mark.parametrize("sha", ["a", "0" * 40])
def test_cli_never_accepts_developer_workspace(monkeypatch, sha):
    m = module()
    monkeypatch.setattr(m.sys, "platform", "linux")
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    monkeypatch.setattr(m.sys, "argv", ["partial_laya", "--sha", sha, "--accept-unknown-lease-loss"])
    with pytest.raises(m.RetirementError):
        m.main()


@pytest.mark.parametrize("flag", ["isolated", "no_site", "dont_write_bytecode", "interpreter"])
def test_cli_requires_isolated_system_python_before_imports(monkeypatch, flag):
    m = module()
    monkeypatch.setattr(m.sys, "platform", "linux")
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    flags = {"isolated": 1, "no_site": 1, "dont_write_bytecode": 1}
    if flag in flags:
        flags[flag] = 0
    monkeypatch.setattr(m.sys, "flags", SimpleNamespace(**flags))
    monkeypatch.setattr(m.sys, "executable", "/tmp/python" if flag == "interpreter" else "/usr/bin/python3.12")
    monkeypatch.setattr(m.sys, "argv", ["partial_laya", "--sha", "e" * 40, "--accept-unknown-lease-loss"])
    monkeypatch.setattr(m.importlib.util, "spec_from_file_location", lambda *a: pytest.fail("must reject before helper imports"))
    with pytest.raises(m.RetirementError, match="canonical explicit operator context"):
        m.main()


@pytest.fixture
def history(tmp_path, monkeypatch):
    m = module()
    record = tmp_path / "partial-laya-closures" / m.FAILED
    record.mkdir(parents=True)
    receipt = "a" * 64
    expected = {"config": {".": {}}, "library": {".": {}}}
    evidence = {"old_sha": m.FAILED, "closing_sha": "d" * 40, "production_sha": m.PRODUCTION,
                "lease_state": m.LEASE_STATE, "baseline": {"verified": True}, "workspace": {"state": "NEEDS_OPERATOR"},
                "partial": {}, "config": {".": {}, "loopback.key": {}}, "library": {".": {}},
                "authorized": {}, "locks": {"original": True}}
    intent = {**evidence, "evidence_sha256": m.digest(evidence),
              "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest()}
    completed = {"state": m.TERMINAL, "old_sha": m.FAILED, "intent_sha256": m.digest(intent), "installation": expected}
    (record / "intent.json").write_text(json.dumps(intent))
    (record / "completed.json").write_text(json.dumps(completed))
    def verify(i, secret):
        if secret is None or hashlib.sha256(secret.encode()).hexdigest() != i["receipt_sha256"]:
            raise m.RetirementError("receipt differs")
    c = SimpleNamespace(verify_receipt=verify, _workspace_unchanged=lambda *a: None)
    b = SimpleNamespace(STATE=tmp_path, CONFIG=tmp_path / "config", INSTALLED=tmp_path / "lib/server.py",
                        _inventory=lambda *a: {}, _read_json=lambda p: json.loads(p.read_text()),
                        canonical_source=lambda sha: tmp_path / sha,
                        _archives=lambda sha: (tmp_path / "oldconfig", tmp_path / "oldlib"),
                        _installation_evidence=lambda *a: expected)
    monkeypatch.setattr(m, "load", lambda *a: c)
    monkeypatch.setattr(m, "baseline", lambda b: ({}, {"verified": True}))
    monkeypatch.setattr(m, "locks", lambda b: {"original": True})
    monkeypatch.setattr(m, "verify_archives", lambda *a: None)
    return m, b, record, receipt


def test_historical_closure_does_not_recheck_current_production(history, monkeypatch):
    m, b, _record, receipt = history
    monkeypatch.setattr(m.Adapter, "live", lambda self: pytest.fail("history cannot depend on future production"))
    result = m.closed_evidence(b, m.FAILED, receipt)
    assert result["state"] == m.TERMINAL
    assert result["workspace"]["state"] == "NEEDS_OPERATOR"


@pytest.mark.parametrize("damage", ["receipt", "no_receipt", "baseline", "locks", "archives", "workspace",
                                  "state", "missing_terminal", "lease_claim", "production", "digest", "conflict"])
def test_historical_closure_rejects_incomplete_or_changed_proofs(history, monkeypatch, damage):
    m, b, record, receipt = history
    if damage == "receipt":
        receipt = "b" * 64
    elif damage == "no_receipt":
        receipt = None
    elif damage == "baseline":
        monkeypatch.setattr(m, "baseline", lambda b: ({}, {"verified": False}))
    elif damage == "locks":
        monkeypatch.setattr(m, "locks", lambda b: {"original": False})
    elif damage in {"archives", "workspace"}:
        def fail(*a):
            raise m.RetirementError("drift")
        if damage == "archives":
            monkeypatch.setattr(m, "verify_archives", fail)
        else:
            monkeypatch.setattr(m, "load", lambda *a: SimpleNamespace(verify_receipt=lambda *a: None, _workspace_unchanged=fail))
    elif damage == "missing_terminal":
        (record / "completed.json").unlink()
    elif damage == "conflict":
        (b.STATE / "unchanged-release-closures" / m.FAILED).mkdir(parents=True)
    elif damage == "state":
        path = record / "completed.json"
        changed = json.loads(path.read_text())
        changed["state"] = "SUCCEEDED"
        path.write_text(json.dumps(changed))
    else:
        path = record / "intent.json"
        changed = json.loads(path.read_text())
        changed[{"lease_claim": "lease_state", "production": "production_sha", "digest": "evidence_sha256"}[damage]] = "changed"
        path.write_text(json.dumps(changed))
    with pytest.raises((m.RetirementError, FileNotFoundError)):
        m.closed_evidence(b, m.FAILED, receipt)
