from datetime import datetime

from app.orchestrator.orchestrator import _build_synthesis_prompt, _specialist_audit_snapshot
from app.orchestrator.schema import SpecialistFinding
from app.twin.schema import HealthTwin, TwinMeta


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
    assert snapshot[0]["support_status"] == "model_inference"
    assert snapshot[0]["evidence_ref_count"] == 0
    assert snapshot[0]["unsupported_reason"] == "missing_system_kb_evidence_refs"
    assert snapshot[0]["evidence_refs"] == []
    assert snapshot[0]["data"]["unsupported"] is True
    assert snapshot[0]["data"]["support_status"] == "model_inference"
    assert snapshot[0]["data"]["evidence_ref_count"] == 0
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
    assert snapshot[0]["support_status"] == "supported"
    assert snapshot[0]["evidence_ref_count"] == 1
    assert snapshot[0]["unsupported_reason"] is None
    assert snapshot[0]["evidence_refs"] == ["claim:c_recovery_low_reduce_intensity"]
    assert snapshot[0]["data"]["unsupported"] is False
    assert snapshot[0]["data"]["support_status"] == "supported"
    assert snapshot[0]["data"]["evidence_ref_count"] == 1


def test_synthesis_prompt_exposes_evidence_contract_to_final_llm():
    finding = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="恢复不足时降低强度",
        findings=[{"title": "今天暂停跑步", "action": "改为散步 20 分钟"}],
        evidence_refs=["claim:c_recovery_low_reduce_intensity"],
    )
    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 5, 17)))

    system_prompt, user_prompt = _build_synthesis_prompt("今天能跑步吗？", twin, [finding])

    assert "系统知识库证据优先" in system_prompt
    assert "support_status=supported" in user_prompt
    assert "evidence_refs=claim:c_recovery_low_reduce_intensity" in user_prompt
