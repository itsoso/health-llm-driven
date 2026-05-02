"""POST /client-events + observability client_events 统计."""
from datetime import datetime, timedelta, timezone

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
    assert stats == {"total": 0, "by_event": {}}
