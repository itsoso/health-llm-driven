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


@pytest.mark.parametrize(
    ("event_name", "meta"),
    [
        ("aigc_media_played", {"media_kind": "video"}),
        (
            "aigc_media_shared",
            {
                "phase": "completed",
                "media_kind": "image",
                "share_target": "xiaohongshu",
            },
        ),
    ],
)
def test_post_client_event_accepts_content_free_aigc_engagement(
    client, db, auth_user_and_headers, event_name, meta,
):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": event_name, "meta": meta},
    )

    assert response.status_code == 202, response.text
    row = db.query(ClientEvent).order_by(ClientEvent.id.desc()).first()
    assert row.event_name == event_name
    assert row.meta == meta


def test_post_client_event_rejects_aigc_resource_identifiers(
    client, auth_user_and_headers,
):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "aigc_media_shared",
            "meta": {
                "phase": "completed",
                "media_kind": "video",
                "share_target": "wechat",
                "job_id": "private-job-id",
            },
        },
    )

    assert response.status_code == 422, response.text


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
        "app_update": {
            "launches": 0,
            "checks": 0,
            "ready": 0,
            "failures": 0,
            "failure_rate_pct": None,
            "by_phase": {},
            "by_launch_source": {},
            "release_health": {
                "status": "observe",
                "sample_sufficient": False,
                "thresholds": {
                    "min_launches": 20,
                    "emergency_rate_pct": 5.0,
                    "terminal_failure_rate_pct": 10.0,
                },
                "launches": 0,
                "emergency_launches": 0,
                "emergency_rate_pct": None,
                "terminal_attempts": 0,
                "terminal_failures": 0,
                "terminal_failure_rate_pct": None,
                "reasons": ["发布启动样本不足 20，继续观察"],
            },
        },
        "starter_ctr": {},
        "home_cold_start_ms": {"n": 0, "p50": None, "p95": None, "incomplete": 0},
        "chat_attachment_pipeline": {
            "attempts": 0,
            "accepted": 0,
            "failures": 0,
            "acceptance_rate_pct": None,
            "image_count_total": 0,
            "failures_by_stage": {},
            "duration_buckets": {},
            "payload_buckets": {},
        },
        "diet_capture_ms": {
            "recognition": {
                "n": 0, "attempts": 0, "p50": None, "p95": None,
                "failures": 0, "cancelled": 0,
                "client_prepare_p50": None, "client_prepare_p95": None,
                "payload_kb_p50": None, "payload_kb_p95": None,
            },
            "confirmation": {
                "n": 0, "attempts": 0, "p50": None, "p95": None,
                "failures": 0, "cancelled": 0,
                "corrected": 0, "correction_rate_pct": None,
            },
            "share": {
                "n": 0, "attempts": 0, "p50": None, "p95": None,
                "failures": 0, "cancelled": 0,
                "by_target": {
                    "generic": {
                        "attempts": 0, "completed": 0, "with_photo": 0, "failures": 0,
                    },
                    "wechat": {
                        "attempts": 0, "completed": 0, "with_photo": 0, "failures": 0,
                    },
                    "xiaohongshu": {
                        "attempts": 0, "completed": 0, "with_photo": 0, "failures": 0,
                    },
                },
            },
        },
    }


@pytest.mark.parametrize("event_name,meta", [
    ("app_update_phase", {
        "phase": "downloading",
        "platform": "ios",
        "channel": "production",
        "runtime": "1.3.1",
        "native_build": "190",
        "update_id": "01234567-89ab-cdef-0123-456789abcdef",
    }),
    ("app_update_terminal", {
        "phase": "ready",
        "duration_bucket": "3_10s",
        "platform": "ios",
        "channel": "production",
    }),
    ("app_update_terminal", {
        "phase": "native_update_required",
        "duration_bucket": "lt_1s",
        "platform": "ios",
        "channel": "production",
    }),
    ("app_update_launch", {
        "launch_source": "ota",
        "platform": "ios",
        "channel": "production",
        "runtime": "1.3.1",
    }),
])
def test_app_update_events_accept_content_free_meta(
    client, db, auth_user_and_headers, event_name, meta
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": event_name, "meta": meta},
    )

    assert response.status_code == 202, response.text
    row = db.query(ClientEvent).order_by(ClientEvent.id.desc()).first()
    assert row.event_name == event_name
    assert row.meta == meta


@pytest.mark.parametrize("event_name,meta", [
    ("app_update_terminal", {
        "phase": "ready",
        "duration_bucket": "3_10s",
        "error_message": "用户的健康数据",
    }),
    ("app_update_launch", {
        "launch_source": "ota",
        "update_id": "file:///private/health.db",
    }),
    ("app_update_phase", {
        "phase": "downloaded",
        "platform": "iOS",
    }),
])
def test_app_update_events_reject_private_or_invalid_meta(
    client, auth_user_and_headers, event_name, meta
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": event_name, "meta": meta},
    )

    assert response.status_code == 422, response.text


def test_client_events_stats_counts_app_update_outcomes(db, auth_user_and_headers):
    from app.models.user import User
    from app.services.observability_service import client_events_stats

    user = db.query(User).first()
    now = datetime.now(timezone.utc)
    db.add_all([
        ClientEvent(user_id=user.id, event_name="app_update_launch", meta={
            "launch_source": "ota",
        }, created_at=now - timedelta(hours=1)),
        ClientEvent(user_id=user.id, event_name="app_update_terminal", meta={
            "phase": "ready", "duration_bucket": "3_10s",
        }, created_at=now - timedelta(hours=1)),
        ClientEvent(user_id=user.id, event_name="app_update_terminal", meta={
            "phase": "failed", "duration_bucket": "gte_30s",
        }, created_at=now - timedelta(hours=2)),
        ClientEvent(user_id=user.id, event_name="app_update_phase", meta={
            "phase": "downloading",
        }, created_at=now - timedelta(hours=2)),
    ])
    db.commit()

    stats = client_events_stats(db, now - timedelta(days=7), user_id=None)

    assert stats["app_update"] == {
        "launches": 1,
        "checks": 2,
        "ready": 1,
        "failures": 1,
        "failure_rate_pct": 50.0,
        "by_phase": {"downloading": 1, "ready": 1, "failed": 1},
        "by_launch_source": {"ota": 1},
        "release_health": {
            "status": "observe",
            "sample_sufficient": False,
            "thresholds": {
                "min_launches": 20,
                "emergency_rate_pct": 5.0,
                "terminal_failure_rate_pct": 10.0,
            },
            "launches": 1,
            "emergency_launches": 0,
            "emergency_rate_pct": 0.0,
            "terminal_attempts": 2,
            "terminal_failures": 1,
            "terminal_failure_rate_pct": 50.0,
            "reasons": ["发布启动样本不足 20，继续观察"],
        },
    }


def test_client_events_stats_does_not_dilute_ota_failure_rate_with_native_gate(
    db, auth_user_and_headers,
):
    from app.services.observability_service import client_events_stats

    user, _ = auth_user_and_headers
    now = datetime.now(timezone.utc)
    events = [
        ClientEvent(user_id=user.id, event_name="app_update_terminal", meta={
            "phase": "ready", "duration_bucket": "3_10s",
        }, created_at=now - timedelta(hours=1))
        for _ in range(18)
    ]
    events.extend(
        ClientEvent(user_id=user.id, event_name="app_update_terminal", meta={
            "phase": "failed", "duration_bucket": "gte_30s",
        }, created_at=now - timedelta(hours=1))
        for _ in range(2)
    )
    events.extend(
        ClientEvent(user_id=user.id, event_name="app_update_terminal", meta={
            "phase": "native_update_required", "duration_bucket": "lt_1s",
        }, created_at=now - timedelta(hours=1))
        for _ in range(10)
    )
    db.add_all(events)
    db.commit()

    stats = client_events_stats(db, now - timedelta(days=7), user_id=None)

    assert stats["app_update"]["checks"] == 30
    assert stats["app_update"]["failure_rate_pct"] == 10.0
    assert stats["app_update"]["release_health"]["terminal_failure_rate_pct"] == 10.0


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
    ("verified_loop", {"cycle_id": 7, "verdict_count": 2, "total": 3}),
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


def test_watch_smart_reminder_visible_event_accepted(client, db, auth_user_and_headers):
    """Watch 成功刷新到某条智能提醒时,必须能上报可见 receipt."""
    _, headers = auth_user_and_headers
    r = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "watch_smart_reminder_visible",
            "meta": {
                "action_id": "agenda-smart_reminder-12",
                "reminder_id": "12",
                "kind": "hydration",
                "surface": "watch_summary",
            },
        },
    )

    assert r.status_code == 202, r.text
    assert r.json()["ok"] is True


@pytest.mark.parametrize("event_name,meta", [
    ("agent_turn_terminal", {
        "phase": "completed",
        "duration_bucket": "3_10s",
    }),
    ("voice_input_terminal", {
        "phase": "cancelled",
        "duration_bucket": "1_3s",
        "action_type": "hold",
    }),
    ("voice_asr_terminal", {
        "phase": "completed",
        "duration_bucket": "1_3s",
        "action_type": "hold",
        "provider": "openai_whisper",
        "confidence": "medium",
        "empty": False,
    }),
    ("write_receipt_terminal", {
        "phase": "verified",
        "duration_bucket": "10_30s",
        "action_type": "diet.update",
        "verified": True,
    }),
])
def test_reliability_terminal_events_accept_privacy_safe_meta(
    client,
    db,
    auth_user_and_headers,
    event_name,
    meta,
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": event_name, "meta": meta},
    )

    assert response.status_code == 202, response.text
    row = db.query(ClientEvent).order_by(ClientEvent.id.desc()).first()
    assert row.event_name == event_name
    assert row.meta == meta


def test_chat_turn_queued_event_accepts_safe_queue_metadata(
    client,
    db,
    auth_user_and_headers,
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "chat_turn_queued",
            "meta": {
                "surface": "mobile",
                "channel": "voice",
                "queue_depth_at_submit": 2,
            },
        },
    )

    assert response.status_code == 202, response.text
    row = db.query(ClientEvent).order_by(ClientEvent.id.desc()).first()
    assert row.event_name == "chat_turn_queued"
    assert row.meta == {
        "surface": "mobile",
        "channel": "voice",
        "queue_depth_at_submit": 2,
    }


def test_chat_attachment_terminal_accepts_content_free_pipeline_metadata(
    client,
    db,
    auth_user_and_headers,
):
    _, headers = auth_user_and_headers
    meta = {
        "phase": "accepted",
        "stage": "server_accept",
        "image_count": 3,
        "duration_bucket": "3_10s",
        "payload_bucket": "1_4mb",
    }
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "chat_attachment_terminal",
            "event_key": "attachment-attempt-001",
            "meta": meta,
        },
    )

    assert response.status_code == 202, response.text
    row = db.query(ClientEvent).order_by(ClientEvent.id.desc()).first()
    assert row.event_name == "chat_attachment_terminal"
    assert row.event_key != "attachment-attempt-001"
    assert len(row.event_key) == 64
    assert row.meta == meta


def test_chat_attachment_terminal_is_idempotent_by_owner_and_event_key(
    client,
    db,
    auth_user_and_headers,
):
    _, headers = auth_user_and_headers
    body = {
        "event_name": "chat_attachment_terminal",
        "event_key": "attachment-attempt-dedup",
        "meta": {
            "phase": "accepted",
            "stage": "server_accept",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
        },
    }

    first = client.post("/api/v1/client-events", headers=headers, json=body)
    second = client.post("/api/v1/client-events", headers=headers, json=body)

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert second.json()["duplicate"] is True
    rows = db.query(ClientEvent).filter(
        ClientEvent.event_name == "chat_attachment_terminal",
    ).all()
    assert len(rows) == 1
    assert rows[0].event_key != "attachment-attempt-dedup"


def test_chat_attachment_terminal_requires_safe_event_key(
    client,
    auth_user_and_headers,
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "chat_attachment_terminal",
            "meta": {
                "phase": "accepted",
                "stage": "server_accept",
                "image_count": 1,
                "duration_bucket": "1_3s",
                "payload_bucket": "lt_256kb",
            },
        },
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "meta",
    [
        {
            "phase": "accepted",
            "stage": "local_prepare",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
        },
        {
            "phase": "accepted",
            "stage": "server_accept",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
            "error_code": "send_rejected",
        },
        {
            "phase": "failed",
            "stage": "server_accept",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
        },
        {
            "phase": "failed",
            "stage": "local_prepare",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "unknown",
            "error_code": "send_rejected",
        },
    ],
)
def test_chat_attachment_terminal_rejects_contradictory_terminal_state(
    client,
    auth_user_and_headers,
    meta,
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "chat_attachment_terminal",
            "event_key": "attachment-state-contract",
            "meta": meta,
        },
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "meta",
    [
        {
            "phase": "accepted",
            "stage": "server_accept",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
            "uri": "file:///private/meal.jpeg",
        },
        {
            "phase": "completed",
            "stage": "server_accept",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
        },
        {
            "phase": "failed",
            "stage": "upload",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
        },
        {
            "phase": "failed",
            "stage": "local_prepare",
            "image_count": 10,
            "duration_bucket": "1_3s",
            "payload_bucket": "unknown",
        },
        {
            "phase": "failed",
            "stage": "server_accept",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
            "error_code": "turn_private_identifier",
        },
        {
            "phase": "failed",
            "stage": "server_accept",
            "image_count": 1,
            "duration_bucket": "1_3s",
            "payload_bucket": "lt_256kb",
            "error_code": ["send_rejected"],
        },
    ],
)
def test_chat_attachment_terminal_rejects_private_or_invalid_metadata(
    client,
    auth_user_and_headers,
    meta,
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
            "event_name": "chat_attachment_terminal",
            "event_key": "attachment-invalid-metadata",
            "meta": meta,
        },
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("meta", [
    {
        "surface": "mobile",
        "channel": "typed",
        "queue_depth_at_submit": 0,
    },
    {
        "surface": "mobile",
        "channel": "typed",
        "queue_depth_at_submit": 51,
    },
    {
        "surface": "mobile",
        "channel": "typed",
        "queue_depth_at_submit": 1,
        "content": "用户健康隐私",
    },
    {
        "surface": "watch",
        "channel": "typed",
        "queue_depth_at_submit": 1,
    },
])
def test_chat_turn_queued_event_rejects_unstable_or_private_metadata(
    client,
    auth_user_and_headers,
    meta,
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": "chat_turn_queued", "meta": meta},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("forbidden_key,forbidden_value", [
    ("content", "用户健康正文"),
    ("audio", "base64-secret"),
    ("uri", "file:///private/voice.m4a"),
    ("resource_id", 42),
])
def test_reliability_terminal_events_reject_private_or_identifying_meta(
    client,
    auth_user_and_headers,
    forbidden_key,
    forbidden_value,
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={
                "event_name": "voice_asr_terminal",
                "meta": {
                    "phase": "completed",
                    "duration_bucket": "1_3s",
                    "action_type": "dictation",
                    "provider": "openai_whisper",
                    "empty": False,
                    forbidden_key: forbidden_value,
                },
            },
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("event_name,meta", [
    ("agent_turn_terminal", {
        "phase": "unknown",
        "duration_bucket": "3_10s",
    }),
    ("voice_input_terminal", {
        "phase": "completed",
        "duration_bucket": "forever",
        "action_type": "dictation",
    }),
    ("voice_input_terminal", {
        "phase": "completed",
        "duration_bucket": "1_3s",
        "action_type": "dictation\nprivate",
    }),
    ("voice_asr_terminal", {
        "phase": "completed",
        "duration_bucket": "1_3s",
        "action_type": "hold",
        "provider": "OpenAI Whisper",
        "empty": False,
    }),
    ("voice_asr_terminal", {
        "phase": "completed",
        "duration_bucket": "1_3s",
        "action_type": "hold",
        "provider": "openai_whisper",
        "confidence": "certain",
        "empty": False,
    }),
    ("write_receipt_terminal", {
        "phase": "verified",
        "duration_bucket": "1_3s",
        "action_type": "diet.update",
        "verified": "yes",
    }),
    ("write_receipt_terminal", {
        "phase": "verified",
        "duration_bucket": "1_3s",
        "action_type": "diet.update",
        "verified": False,
    }),
    ("write_receipt_terminal", {
        "phase": "unverified",
        "duration_bucket": "1_3s",
        "action_type": "diet.update",
        "verified": True,
    }),
])
def test_reliability_terminal_events_reject_invalid_contract(
    client,
    auth_user_and_headers,
    event_name,
    meta,
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": event_name, "meta": meta},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("event_name,meta", [
    ("diet_photo_recognition_terminal", {
        "phase": "completed",
        "duration_ms": 4321,
        "server_total_ms": 3890,
        "client_prepare_ms": 125,
        "payload_bytes": 482_304,
        "food_count": 2,
        "table_calibrated_count": 1,
    }),
    ("diet_photo_confirmation_terminal", {
        "phase": "completed",
        "duration_ms": 640,
        "verified": True,
        "corrected": False,
    }),
    ("diet_share_terminal", {
        "phase": "completed",
        "duration_ms": 920,
        "has_photo": True,
        "share_target": "xiaohongshu",
    }),
])
def test_diet_capture_events_accept_only_numeric_privacy_safe_metrics(
    client, db, auth_user_and_headers, event_name, meta
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": event_name, "meta": meta},
    )

    assert response.status_code == 202, response.text
    row = db.query(ClientEvent).order_by(ClientEvent.id.desc()).first()
    assert row.event_name == event_name
    assert row.meta == meta


@pytest.mark.parametrize("meta", [
    {"phase": "completed", "duration_ms": 920, "has_photo": True, "share_target": "wechat-private"},
    {"phase": "completed", "duration_ms": 920, "has_photo": True, "share_target": "xiaohongshu", "caption": "private meal"},
])
def test_diet_share_events_reject_invalid_or_private_target_meta(
    client, auth_user_and_headers, meta
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": "diet_share_terminal", "meta": meta},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("meta", [
    {"phase": "completed", "duration_ms": -1, "food_count": 1, "table_calibrated_count": 0},
    {"phase": "completed", "duration_ms": 100, "food_count": 1, "table_calibrated_count": 2},
    {"phase": "completed", "duration_ms": 100, "food_count": 1, "table_calibrated_count": 0,
     "food_items": "private meal"},
    {"phase": "completed", "duration_ms": 100, "client_prepare_ms": 100,
     "payload_bytes": 20 * 1024 * 1024 + 1, "food_count": 1, "table_calibrated_count": 0},
])
def test_diet_capture_events_reject_invalid_or_private_meta(
    client, auth_user_and_headers, meta
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/client-events",
        headers=headers,
        json={"event_name": "diet_photo_recognition_terminal", "meta": meta},
    )

    assert response.status_code == 422, response.text
