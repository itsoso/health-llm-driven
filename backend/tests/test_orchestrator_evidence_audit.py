from app.orchestrator.orchestrator import _specialist_audit_snapshot
from app.orchestrator.schema import SpecialistFinding


def test_specialist_audit_snapshot_marks_unsupported_when_no_evidence_refs():
    finding = SpecialistFinding(
        specialist_name="fuel_strategist",
        category="nutrition",
        summary="提高蛋白质摄入",
        findings=[{"title": "今天蛋白质目标 113g"}],
        raw={"recommendations": ["蛋白质优先"]},
    )

    snapshot = _specialist_audit_snapshot([finding])

    assert snapshot[0]["unsupported"] is True
    assert snapshot[0]["evidence_refs"] == []
    assert snapshot[0]["data"]["unsupported"] is True
    assert snapshot[0]["data"]["unsupported_reason"] == "missing_system_kb_evidence_refs"


def test_specialist_audit_snapshot_preserves_supported_evidence_refs():
    finding = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="恢复不足时降低强度",
        findings=[{"title": "降低跑步强度", "evidence_refs": ["claim:c_recovery_low_reduce_intensity"]}],
        raw={},
        evidence_refs=["claim:c_recovery_low_reduce_intensity"],
    )

    snapshot = _specialist_audit_snapshot([finding])

    assert snapshot[0]["unsupported"] is False
    assert snapshot[0]["evidence_refs"] == ["claim:c_recovery_low_reduce_intensity"]
    assert snapshot[0]["data"]["unsupported"] is False
