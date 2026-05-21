"""HTTP endpoints 测试 — /reasoning-trace/safety/{id} + /specialist/{id}."""
import logging
from datetime import datetime, timezone

from app.models.agent_audit_log import AgentAuditLog


def _seed_safety(db, user_id: int):
    row = AgentAuditLog(
        user_id=user_id, agent_type="safety_guardian", action="evaluate",
        alerts_count=1, result_summary="1med",
        result_detail={"alerts": [{
            "rule_id": "acute_hrv_drop", "category": "vitals", "severity": 2,
            "title": "HRV 急剧下降", "message": "HRV=28",
            "data_citation": {"hrv": 28},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }]},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _seed_specialist(db, user_id: int):
    row = AgentAuditLog(
        user_id=user_id, agent_type="specialist_batch", action="run",
        findings_count=1, result_summary="1 finding",
        result_detail={"findings": [{
            "specialist": "recovery_coach", "kind": "recovery",
            "summary": "readiness=54 偏低",
            "data": {"readiness": 54}, "proposed_cards": [],
        }]},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_safety_explain_endpoint_200(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    audit = _seed_safety(db, user_id=user.id)

    r = client.get(
        f"/api/v1/reasoning-trace/safety/{audit.id}?rule_id=acute_hrv_drop",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "safety"
    assert body["rule"]["name"] == "acute_hrv_drop"
    assert "twin_evidence" in body
    assert "related_facts" in body
    assert "confidence" in body


def test_safety_explain_logs_audit_context(client, db, auth_user_and_headers, caplog):
    user, headers = auth_user_and_headers
    audit = _seed_safety(db, user_id=user.id)

    with caplog.at_level(logging.INFO, logger="app.api.reasoning_trace"):
        r = client.get(
            f"/api/v1/reasoning-trace/safety/{audit.id}?rule_id=acute_hrv_drop",
            headers=headers,
        )

    assert r.status_code == 200, r.text
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        f"[reasoning-trace] safety audit_id={audit.id}" in message
        and "rule_id=acute_hrv_drop" in message
        for message in messages
    )


def test_safety_explain_cross_user_returns_404(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    # seed 一个**别的** user 的 audit
    audit = _seed_safety(db, user_id=9999)
    r = client.get(
        f"/api/v1/reasoning-trace/safety/{audit.id}?rule_id=acute_hrv_drop",
        headers=headers,
    )
    assert r.status_code == 404


def test_safety_explain_rule_missing_404(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    audit = _seed_safety(db, user_id=user.id)
    r = client.get(
        f"/api/v1/reasoning-trace/safety/{audit.id}?rule_id=does_not_exist",
        headers=headers,
    )
    assert r.status_code == 404


def test_safety_explain_requires_rule_id(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    audit = _seed_safety(db, user_id=user.id)
    # 不传 rule_id query param
    r = client.get(
        f"/api/v1/reasoning-trace/safety/{audit.id}",
        headers=headers,
    )
    assert r.status_code == 422  # FastAPI validation


def test_safety_explain_unauthenticated_401(client, db):
    audit = _seed_safety(db, user_id=1)
    r = client.get(
        f"/api/v1/reasoning-trace/safety/{audit.id}?rule_id=acute_hrv_drop",
    )
    assert r.status_code in (401, 403)


def test_specialist_explain_endpoint_200(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    audit = _seed_specialist(db, user_id=user.id)

    r = client.get(
        f"/api/v1/reasoning-trace/specialist/{audit.id}?specialist=recovery_coach",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "specialist"
    assert body["specialist"] == "recovery_coach"
    assert "data" in body
    assert "confidence" in body


def test_specialist_explain_logs_audit_context(client, db, auth_user_and_headers, caplog):
    user, headers = auth_user_and_headers
    audit = _seed_specialist(db, user_id=user.id)

    with caplog.at_level(logging.INFO, logger="app.api.reasoning_trace"):
        r = client.get(
            f"/api/v1/reasoning-trace/specialist/{audit.id}?specialist=recovery_coach",
            headers=headers,
        )

    assert r.status_code == 200, r.text
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        f"[reasoning-trace] specialist audit_id={audit.id}" in message
        and "specialist=recovery_coach" in message
        for message in messages
    )


def test_specialist_explain_cross_user_404(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    audit = _seed_specialist(db, user_id=9999)
    r = client.get(
        f"/api/v1/reasoning-trace/specialist/{audit.id}?specialist=recovery_coach",
        headers=headers,
    )
    assert r.status_code == 404
