from datetime import datetime, timezone
from app.models.agent_audit_log import AgentAuditLog
from app.services.reasoning_explainer import (
    explain_safety_alert,
    explain_specialist_finding,
)


def _seed_safety_audit(db, user_id=1, rule_id="acute_hrv_drop"):
    row = AgentAuditLog(
        user_id=user_id, agent_type="safety_guardian", action="evaluate",
        alerts_count=1, result_summary="1med",
        result_detail={"alerts": [{
            "rule_id": rule_id, "category": "vitals", "severity": 2,
            "title": "HRV 急剧下降", "message": "HRV=28",
            "data_citation": {"hrv": 28, "baseline": 50},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }]},
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_explain_safety_alert_returns_rule_and_evidence(db):
    audit = _seed_safety_audit(db)
    result = explain_safety_alert(db, audit_id=audit.id, rule_id="acute_hrv_drop", user_id=1)

    assert result["source"] == "safety"
    assert result["rule"]["name"] == "acute_hrv_drop"
    assert result["rule"]["category"] == "vitals"
    assert isinstance(result["twin_evidence"], list)
    assert isinstance(result["related_facts"], list)
    assert "confidence_note" in result


def test_explain_safety_alert_cross_user_returns_404_not_403(db):
    # 防枚举: 跨用户访问不返 403 (会泄露 audit ID 的存在性和所有者), 而是统一 404
    audit = _seed_safety_audit(db, user_id=1)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        explain_safety_alert(db, audit_id=audit.id, rule_id="acute_hrv_drop", user_id=2)
    assert exc.value.status_code == 404
    assert "audit 记录不存在或已过期" in exc.value.detail


def test_explain_safety_alert_rule_not_found(db):
    audit = _seed_safety_audit(db)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        explain_safety_alert(db, audit_id=audit.id, rule_id="nonexistent_rule", user_id=1)
    assert exc.value.status_code == 404


def test_explain_safety_alert_memory_fact_timeout_no_throw(db, monkeypatch):
    audit = _seed_safety_audit(db)

    def _boom(*a, **kw):
        raise TimeoutError("bm25 too slow")

    monkeypatch.setattr(
        "app.services.reasoning_explainer.hybrid_retrieve", _boom
    )
    result = explain_safety_alert(db, audit_id=audit.id, rule_id="acute_hrv_drop", user_id=1)
    assert result["related_facts"] == []


def test_explain_specialist_finding_basic(db):
    audit = AgentAuditLog(
        user_id=1, agent_type="specialist_batch", action="run",
        findings_count=1, result_summary="1 finding",
        result_detail={"findings": [{
            "specialist": "recovery_coach", "kind": "readiness",
            "summary": "readiness=54",
            "data": {"readiness": 54, "hrv": 28}, "proposed_cards": [],
        }]},
    )
    db.add(audit); db.commit(); db.refresh(audit)

    result = explain_specialist_finding(
        db, audit_id=audit.id, specialist="recovery_coach", user_id=1
    )
    assert result["source"] == "specialist"
    assert result["specialist"] == "recovery_coach"
    assert result["summary"].startswith("readiness")
    assert "twin_evidence" in result


def test_explain_safety_alert_unknown_audit_id_404(db):
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        explain_safety_alert(db, audit_id=99999, rule_id="x", user_id=1)
    assert exc.value.status_code == 404


def test_explain_specialist_finding_uses_kind_to_partition_mapping(db):
    # Fix 2 回归: kind="fuel" 应该走 body_composition 分区, 不是硬编码 physiological
    audit = AgentAuditLog(
        user_id=1, agent_type="specialist_batch", action="run",
        findings_count=1, result_summary="1 finding",
        result_detail={"findings": [{
            "specialist": "fuel_strategist", "kind": "fuel",
            "summary": "TDEE 缺口 400kcal",
            "data": {"tdee": 2400, "intake": 2000}, "proposed_cards": [],
        }]},
    )
    db.add(audit); db.commit(); db.refresh(audit)

    result = explain_specialist_finding(
        db, audit_id=audit.id, specialist="fuel_strategist", user_id=1
    )
    # twin_evidence 可能为空 (seed 没建真 twin 数据), 但若有任何 item, 其 partition 必须是 body_composition
    for item in result["twin_evidence"]:
        assert item["partition"] == "body_composition", (
            f"kind='fuel' 应映射 body_composition, 实际拿到: {item['partition']}"
        )


def test_explain_response_has_structured_confidence(db):
    # Fix 5 回归: response 同时包含 confidence_note (人读) 和 confidence (机器/Mobile 用)
    audit = _seed_safety_audit(db)
    result = explain_safety_alert(
        db, audit_id=audit.id, rule_id="acute_hrv_drop", user_id=1
    )
    assert "confidence_note" in result
    assert "confidence" in result
    assert result["confidence"]["twin_field_count"] == len(result["twin_evidence"])
    assert result["confidence"]["memory_fact_count"] == len(result["related_facts"])
