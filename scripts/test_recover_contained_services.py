"""Offline recovery orchestration regressions; never contact production."""
import importlib.util
import json
from pathlib import Path

import pytest


def load():
    path = Path(__file__).with_name("recover_contained_services.py")
    spec = importlib.util.spec_from_file_location("recovery_operator_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Proof:
    failed_sha = "a" * 40
    production_sha = "b" * 40

    def __init__(self):
        self.value = {"unchanged": True}
        self.events = []

    def snapshot(self):
        self.events.append("snapshot")
        return self.value.copy()

    def stopped(self):
        self.events.append("stopped")


def setup(monkeypatch, tmp_path):
    module = load()
    proof = Proof()
    monkeypatch.setattr(module, "_systemctl", lambda action, unit: proof.events.append(action))
    monkeypatch.setattr(module, "_wait_ready", lambda p: p.events.append("stable") or {"pids": [1]})
    monkeypatch.setattr(module, "_application_probes", lambda *a: proof.events.append("probes"))
    monkeypatch.setattr(module, "_http_probes", lambda: proof.events.append("http"))
    return module, proof, tmp_path / "audit"


def test_inspection_never_creates_audit_or_starts(monkeypatch, tmp_path):
    m, p, audit = setup(monkeypatch, tmp_path)
    result = m.recover_services(p, audit, "c" * 40)
    assert result["state"] == "INSPECTED"
    assert not audit.exists()
    assert "start" not in p.events


def test_mismatched_evidence_blocks_before_intent(monkeypatch, tmp_path):
    m, p, audit = setup(monkeypatch, tmp_path)
    with pytest.raises(m.RecoveryError):
        m.recover_services(p, audit, "c" * 40, "0" * 64)
    assert not audit.exists()
    assert "start" not in p.events


def test_success_keeps_original_evidence_and_persists_intent_before_start(monkeypatch, tmp_path):
    m, p, audit = setup(monkeypatch, tmp_path)
    inspected = m.recover_services(p, audit, "c" * 40)
    def command(action, unit):
        assert (audit / "intent.json").is_file()
        p.events.append(action)
    monkeypatch.setattr(m, "_systemctl", command)
    result = m.recover_services(p, audit, "c" * 40, inspected["evidence_sha256"])
    assert result["state"] == "RESTORED_PREVIOUS_SERVICES"
    assert p.events.count("start") == 4
    assert "stop" not in p.events
    assert p.events.count("stable") == 2
    assert json.loads((audit / "completed.json").read_text()) == result
    with pytest.raises(m.RecoveryError):
        m.recover_services(p, audit, "c" * 40, inspected["evidence_sha256"])


@pytest.mark.parametrize("failure", ["start", "stable", "probes", "http", "completion"])
def test_failure_preserves_intent_contains_and_never_returns_success(monkeypatch, tmp_path, failure):
    m, p, audit = setup(monkeypatch, tmp_path)
    digest = m.recover_services(p, audit, "c" * 40)["evidence_sha256"]
    if failure == "start":
        def command(action, unit):
            p.events.append(action)
            if action == "start":
                raise RuntimeError("offline failure")
        monkeypatch.setattr(m, "_systemctl", command)
    elif failure == "completion":
        original = m._write
        def write(path, data):
            if path.name == "completed.json":
                raise OSError("offline fsync failure")
            return original(path, data)
        monkeypatch.setattr(m, "_write", write)
    else:
        name = {"stable": "_wait_ready", "probes": "_application_probes", "http": "_http_probes"}[failure]
        monkeypatch.setattr(m, name, lambda *a: (_ for _ in ()).throw(RuntimeError("offline failure")))
    with pytest.raises(m.RecoveryError):
        m.recover_services(p, audit, "c" * 40, digest)
    assert (audit / "intent.json").exists()
    assert p.events.count("stop") == (0 if failure == "probes" else 4)
    assert p.events[-1] == "stopped"


def test_intent_failure_cannot_start_services(monkeypatch, tmp_path):
    m, p, audit = setup(monkeypatch, tmp_path)
    digest = m.recover_services(p, audit, "c" * 40)["evidence_sha256"]
    monkeypatch.setattr(m, "_write", lambda *a: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(OSError):
        m.recover_services(p, audit, "c" * 40, digest)
    assert "start" not in p.events


def test_drift_after_intent_blocks_start(monkeypatch, tmp_path):
    m, p, audit = setup(monkeypatch, tmp_path)
    digest = m.recover_services(p, audit, "c" * 40)["evidence_sha256"]
    original = m._write
    def write(path, data):
        original(path, data)
        if path.name == "intent.json":
            p.value = {"unchanged": False}
    monkeypatch.setattr(m, "_write", write)
    with pytest.raises(m.RecoveryError):
        m.recover_services(p, audit, "c" * 40, digest)
    assert "start" not in p.events


def test_readiness_requires_stability_and_has_a_deadline(monkeypatch):
    m = load()
    now = [0]
    monkeypatch.setattr(m.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(m.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    p = Proof()
    p.running_snapshot = lambda: {"pid": now[0] if now[0] < 4 else 4}
    assert m._wait_ready(p) == {"pid": 4}
    assert now[0] >= 11
    p.running_snapshot = lambda: {"pid": now[0]}
    with pytest.raises(m.RecoveryError):
        m._wait_ready(p)
    assert now[0] <= 72


def test_operator_does_not_echo_invalid_secret_bearing_arguments(monkeypatch, capsys):
    m = load()
    marker = "private-argument-must-not-be-logged"
    monkeypatch.setattr(m.sys, "argv", ["operator", "--unknown", marker])
    assert m.main() == 1
    captured = capsys.readouterr()
    assert marker not in captured.out + captured.err


def test_probe_child_does_not_consume_new_release_permissions():
    m = load()
    import inspect
    body = inspect.getsource(m._probe_child)
    assert "verify_ci=False" in body
    assert "_validate_effective_target" in body
    assert "schema.main()" in body
    assert '"--phase", "staged"' in body
