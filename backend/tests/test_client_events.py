"""POST /client-events + observability client_events 统计."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.client_event import ClientEvent


def test_post_client_event_accepts_whitelisted(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    r = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "reasoning_sheet_opened",
            "meta": {"rule_id": "acute_hrv_drop"},
        },
    )
    assert r.status_code == 202, r.text
    assert r.json()["ok"] is True

    rows = db.query(ClientEvent).all()
    assert len(rows) == 1
    assert rows[0].event_name == "reasoning_sheet_opened"
    assert rows[0].meta == {"rule_id": "acute_hrv_drop"}


def test_post_client_event_rejects_unknown_name(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    r = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": "totally_fake_event"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "allowed" in detail
    assert "reasoning_sheet_opened" in detail["allowed"]


def test_post_client_event_without_meta_ok(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    r = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": "journal_timeline_entered"},
    )
    assert r.status_code == 202
    assert r.json()["ok"] is True
    rows = db.query(ClientEvent).all()
    assert rows[0].meta is None


def test_post_client_event_rejects_oversized_meta(client, auth_user_and_headers):
    """防滥用: meta 不允许塞超大 JSON（避免 DB/日志/网络被打爆）."""
    _, headers = auth_user_and_headers
    r = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "reasoning_sheet_opened",
            "meta": {"blob": "x" * 5000},
        },
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert any("meta too large" in (e.get("msg") or "") for e in detail), detail


def test_client_events_stats_counts_by_event(db, auth_user_and_headers):
    from app.models.user import User
    from app.services.observability_service import client_events_stats

    user = db.query(User).first()
    now = datetime.now(timezone.utc)
    db.add_all([
        ClientEvent(user_id=user.id, event_name="reasoning_sheet_opened",
                    created_at=now - timedelta(hours=1)),
        ClientEvent(user_id=user.id, event_name="reasoning_sheet_opened",
                    created_at=now - timedelta(hours=2)),
        ClientEvent(user_id=user.id, event_name="journal_timeline_entered",
                    created_at=now - timedelta(hours=3)),
    ])
    db.commit()

    since = now - timedelta(days=7)
    stats = client_events_stats(db, since, user_id=None)
    assert stats["total"] == 3
    assert stats["by_event"]["reasoning_sheet_opened"] == 2
    assert stats["by_event"]["journal_timeline_entered"] == 1


def test_client_events_stats_empty(db):
    from app.services.observability_service import client_events_stats

    since = datetime.now(timezone.utc) - timedelta(days=7)
    stats = client_events_stats(db, since, user_id=None)
    assert stats == {
        "total": 0,
        "by_event": {},
        "starter_ctr": {},
        "home_cold_start_ms": {"n": 0, "p50": None, "p95": None, "incomplete": 0},
    }


# ─────────────── Phase 0.4: 5 种新事件白名单 ───────────────


@pytest.mark.parametrize("event_name,meta", [
    ("home_chip_clicked", {"chip": "trust_hero", "target": "/specialist/recovery_coach"}),
    ("home_chip_clicked", {"chip": "specialist", "target": "fuel_strategist"}),
    ("action_card_executed", {"card_id": 12, "action": "execute"}),
    ("action_card_executed", {"card_id": 12, "action": "complete"}),
    ("action_card_executed", {"card_id": 12, "action": "reminder"}),
    ("push_notification_opened", {"kind": "lab_overdue", "deep_link": "health://medical-exams/upload"}),
    ("chat_message_sent", {"source": "chat", "has_image": False}),
    ("chat_message_sent", {"source": "voice", "has_image": False}),
    ("chat_message_sent", {"source": "siri", "has_image": False}),
    ("quick_record_logged", {"kind": "weight"}),
    ("quick_record_logged", {"kind": "bp"}),
    ("quick_record_logged", {"kind": "medication"}),
])
def test_phase_0_4_new_events_accepted(client, db, auth_user_and_headers, event_name, meta):
    """Phase 0.4 新增的 5 种事件名 + 各自 meta 应被白名单接受."""
    _, headers = auth_user_and_headers
    r = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": event_name, "meta": meta},
    )
    assert r.status_code == 202, f"{event_name} 被拒, body={r.text}"
    assert r.json()["ok"] is True


def test_phase_0_4_all_5_events_in_allowed_list(client, auth_user_and_headers):
    """反向: 故意发不在白名单的 fake 事件, 错误响应应该列出新 5 种作为合法选项."""
    _, headers = auth_user_and_headers
    r = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": "_definitely_fake_"},
    )
    assert r.status_code == 400
    allowed = r.json()["detail"]["allowed"]
    for evt in [
        "home_chip_clicked",
        "action_card_executed",
        "push_notification_opened",
        "chat_message_sent",
        "quick_record_logged",
    ]:
        assert evt in allowed, f"白名单缺 {evt}"


@pytest.mark.parametrize("event_name", [
    "watch_action_shown",
    "watch_action_completed",
    "watch_action_snoozed",
    "watch_action_skipped",
    "watch_action_failed",
])
def test_watch_action_events_accepted(client, db, auth_user_and_headers, event_name):
    """Watch top_action 必须能上报 shown/complete/snooze/skip/fail,否则无法算闭环."""
    _, headers = auth_user_and_headers
    r = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": event_name,
            "meta": {
                "action_id": "agenda-health_protocol-12",
                "kind": "medication",
                "priority_tier": "P1",
            },
        },
    )
    assert r.status_code == 202, f"{event_name} 被拒, body={r.text}"
    assert r.json()["ok"] is True
