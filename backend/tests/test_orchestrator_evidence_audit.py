from datetime import datetime

from app.orchestrator.orchestrator import (
    _apply_planner_evidence_policy,
    _build_synthesis_prompt,
    _specialist_audit_snapshot,
)
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


def test_specialist_audit_snapshot_uses_existing_evidence_resolution_when_present():
    finding = SpecialistFinding(
        specialist_name="fuel_strategist",
        category="nutrition",
        summary="晚餐已记录，热量基本平衡",
        findings=[{"title": "晚餐记录"}],
        raw={
            "evidence_resolution": {
                "evidence_refs": [],
                "support_status": "not_applicable",
                "unsupported": False,
                "unsupported_reason": None,
                "matched_claim_count": 0,
                "resolver": "system_kb_v1",
            }
        },
    )

    snapshot = _specialist_audit_snapshot([finding])

    assert snapshot[0]["support_status"] == "not_applicable"
    assert snapshot[0]["unsupported"] is False
    assert snapshot[0]["unsupported_reason"] is None
    assert snapshot[0]["data"]["support_status"] == "not_applicable"
    assert snapshot[0]["data"]["unsupported"] is False
    assert snapshot[0]["data"]["evidence_resolution"]["support_status"] == "not_applicable"


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


def test_planner_evidence_policy_blocks_unsupported_same_category_action():
    supported = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="恢复不足，今天暂停跑步",
        findings=[{"title": "今天暂停跑步", "action": "改为散步 20 分钟"}],
        evidence_refs=["claim:c_recovery_low_reduce_intensity"],
    )
    unsupported = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="今天可以轻松跑 30 分钟",
        findings=[{"title": "轻松跑 30 分钟", "action": "Z1 慢跑"}],
    )

    filtered, trace = _apply_planner_evidence_policy([unsupported, supported])

    assert filtered == [supported]
    assert trace["blocked_count"] == 1
    assert trace["blocked"][0]["specialist"] == "movement_coach"
    assert trace["blocked"][0]["reason"] == "unsupported_actionable_same_category_has_supported_kb"
    assert unsupported.raw["planner_evidence_policy"]["blocked"] is True


def test_planner_evidence_policy_blocks_unsupported_same_evidence_domain_action():
    supported_recovery = SpecialistFinding(
        specialist_name="recovery_coach",
        category="recovery",
        summary="恢复不足，今天不跑",
        findings=[{"title": "暂停跑步", "action": "只做轻量活动"}],
        evidence_refs=["claim:c_recovery_low_reduce_intensity"],
    )
    unsupported_movement = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="可以安排 30 分钟跑步",
        findings=[{"title": "跑步 30 分钟", "action": "Z1 慢跑"}],
    )

    filtered, trace = _apply_planner_evidence_policy([unsupported_movement, supported_recovery])

    assert filtered == [supported_recovery]
    assert trace["blocked_count"] == 1
    assert trace["blocked"][0]["evidence_domain"] == "training_recovery"


def test_planner_evidence_policy_keeps_unsupported_safety_alerts():
    supported = SpecialistFinding(
        specialist_name="movement_coach",
        category="movement",
        summary="恢复不足，今天暂停跑步",
        findings=[{"title": "今天暂停跑步"}],
        evidence_refs=["claim:c_recovery_low_reduce_intensity"],
    )
    safety = SpecialistFinding(
        specialist_name="safety_guardian",
        category="safety",
        summary="夜间血氧过低，需要就医确认",
        findings=[
            {
                "title": "夜间血氧过低",
                "severity_label": "red",
                "action": "尽快咨询医生",
            }
        ],
    )

    filtered, trace = _apply_planner_evidence_policy([safety, supported])

    assert filtered == [safety, supported]
    assert trace["blocked_count"] == 0
    assert safety.raw.get("planner_evidence_policy", {}).get("kept_reason") == "safety_or_data_gap"
