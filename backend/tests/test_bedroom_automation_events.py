"""卧室自动化事件: service + webhook API + 审计 (设计文档 §7/§10/§11).

覆盖:
- record_event → get_events (时间倒序, 用户隔离)
- record_event 写一条 AuditLog (旁路成功 → audit_ref 回填)
- event_type 缺失 → ValueError (不静默写垃圾行)
- 未知 source 回退 ha
- webhook 200 + shape + 401 (无 token) + 用户隔离
- webhook event_type 缺失 → 400
- 摄入失败上抛 (DB 写入异常 → service raise / API 500)
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from app.models.user import User
from app.services import bedroom_environment_service as svc
from app.services.auth import auth_service


def _make_user(db) -> User:
    u = User(
        username=f"bevt_{uuid.uuid4().hex[:8]}",
        email=f"bevt_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="bedevt",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers(user: User):
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────── service ───────────────────────────

def test_record_then_get_events(db):
    u = _make_user(db)
    svc.record_event(
        db,
        u.id,
        {
            "event_type": "ventilation_boost",
            "reason": "CO2 1280ppm 持续 10 分钟",
            "command_entity_id": "fan.bedroom_fresh_air",
            "command_mode": "high",
            "source": "ha",
        },
    )
    events = svc.get_events(db, u.id, days=7)
    assert len(events) == 1
    e = events[0]
    assert e["event_type"] == "ventilation_boost"
    assert e["command_entity_id"] == "fan.bedroom_fresh_air"
    assert e["command_mode"] == "high"
    assert e["source"] == "ha"
    assert e["room_id"] == "bedroom"
    assert e["manual_override"] is False


def test_get_events_desc_order(db):
    u = _make_user(db)
    svc.record_event(db, u.id, {"event_type": "first"})
    svc.record_event(db, u.id, {"event_type": "second"})
    events = svc.get_events(db, u.id, days=7)
    assert [e["event_type"] for e in events] == ["second", "first"]


def test_event_writes_audit_and_backfills_ref(db):
    """record_event 写一条 AuditLog (agent_type=bedroom_automation) 且回填 audit_ref."""
    from app.models.agent_audit_log import AgentAuditLog

    u = _make_user(db)
    event = svc.record_event(db, u.id, {"event_type": "scene_triggered", "source": "reva"})

    logs = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.user_id == u.id,
            AgentAuditLog.agent_type == "bedroom_automation",
        )
        .all()
    )
    assert len(logs) == 1
    assert event.audit_ref == str(logs[0].id)
    assert logs[0].action == "scene_triggered"


def test_event_type_required(db):
    u = _make_user(db)
    import pytest

    with pytest.raises(ValueError):
        svc.record_event(db, u.id, {"reason": "no type"})
    with pytest.raises(ValueError):
        svc.record_event(db, u.id, {"event_type": "   "})


def test_unknown_source_falls_back_ha(db):
    u = _make_user(db)
    event = svc.record_event(db, u.id, {"event_type": "x", "source": "garbage"})
    assert event.source == "ha"


def test_manual_override_flag(db):
    u = _make_user(db)
    event = svc.record_event(
        db, u.id, {"event_type": "manual_override", "manual_override": True, "source": "manual"}
    )
    assert event.manual_override is True
    assert event.source == "manual"


def test_audit_failure_does_not_block_event(db):
    """审计写入失败时, 事件仍落库 (审计是旁路, 不反向阻断摄入)."""
    u = _make_user(db)
    with patch(
        "app.agents.audit.log_bedroom_event", side_effect=RuntimeError("audit down")
    ):
        event = svc.record_event(db, u.id, {"event_type": "ventilation_boost"})
    assert event.id is not None
    assert event.audit_ref is None
    # 事件确实落库了.
    assert len(svc.get_events(db, u.id, days=7)) == 1


def test_record_failure_raises(db):
    """主事件 DB 写入失败必须上抛 (让客户端感知, 不假装成功)."""
    import pytest

    u = _make_user(db)
    with patch.object(db, "commit", side_effect=RuntimeError("db down")):
        with pytest.raises(RuntimeError):
            svc.record_event(db, u.id, {"event_type": "ventilation_boost"})


# ─────────────────────────── webhook API ───────────────────────────

def test_webhook_ingest_and_get(client, db):
    u = _make_user(db)
    headers = _headers(u)
    resp = client.post(
        "/api/v1/integrations/home-assistant/webhook",
        headers=headers,
        json={
            "event_type": "ventilation_boost",
            "reason": "CO2 1300ppm",
            "command_entity_id": "fan.bedroom_fresh_air",
            "command_mode": "boost",
            "source": "ha",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["event_type"] == "ventilation_boost"
    assert body["source"] == "ha"
    assert body["audit_ref"] is not None
    assert "id" in body

    events = svc.get_events(db, u.id, days=7)
    assert len(events) == 1


def test_webhook_requires_auth(client):
    assert (
        client.post(
            "/api/v1/integrations/home-assistant/webhook",
            json={"event_type": "x"},
        ).status_code
        == 401
    )


def test_webhook_missing_event_type_is_400(client, db):
    u = _make_user(db)
    headers = _headers(u)
    resp = client.post(
        "/api/v1/integrations/home-assistant/webhook",
        headers=headers,
        json={"reason": "no type"},
    )
    assert resp.status_code == 400, resp.text


def test_webhook_user_isolation(client, db):
    u1 = _make_user(db)
    u2 = _make_user(db)
    client.post(
        "/api/v1/integrations/home-assistant/webhook",
        headers=_headers(u1),
        json={"event_type": "u1_event"},
    )
    # u2 通过 service 查不到 u1 的事件.
    assert svc.get_events(db, u2.id, days=7) == []
    assert len(svc.get_events(db, u1.id, days=7)) == 1


def test_webhook_failure_propagates_500(client, db):
    """service 写入失败 → API 500 (摄入失败让客户端感知)."""
    u = _make_user(db)
    headers = _headers(u)
    with patch(
        "app.services.bedroom_environment_service.record_event",
        side_effect=RuntimeError("db down"),
    ):
        resp = client.post(
            "/api/v1/integrations/home-assistant/webhook",
            headers=headers,
            json={"event_type": "ventilation_boost"},
        )
    assert resp.status_code == 500, resp.text
