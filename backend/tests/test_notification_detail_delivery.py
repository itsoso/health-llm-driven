"""A tap's persisted notification ID exists before delivery and survives replay."""
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import NotificationLog, UserNotificationSetting
from app.models.user import User
from app.services.notification.deeplinks import history_deeplink
from app.services.notification.push_service import PushService


@pytest.fixture
def sender(db):
    user = User(name="Detail delivery", username="detail_delivery", email="detail_delivery@example.test", hashed_password="x")
    db.add(user)
    db.commit()
    db.add(UserNotificationSetting(user_id=user.id, enabled=True, ios_push_enabled=True,
                                   ios_device_token="test-token", quiet_hours_start="22:00",
                                   quiet_hours_end="09:00", ai_advice_enabled=True))
    db.commit()
    return PushService(db), user.id


@pytest.mark.parametrize("data,expected", [
    ({}, "/notification-history?detailId=7"),
    ({"deep_link": "/diet"}, "/diet"),
    ({"deeplink": "health://card/3"}, "health://card/3"),
    ({"kind": "protocol", "category": "AGENDA_ACTION"}, "/agenda"),
    ({"reminder_type": "medication"}, None),
    ({"kind": "medication_reminder"}, None),
    ({"category": "MEDICATION_REMINDER"}, None),
    ({"screen": "sleep"}, None),
    ({"screen": "home"}, "/notification-history?detailId=7"),
    ({"workout_id": 42}, "/notification-history?detailId=7"),
])
def test_history_fallback_preserves_specialized_destinations(data, expected):
    assert history_deeplink("reminder", data, log_id=7) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_success", [True, False])
async def test_detail_record_committed_before_channel_and_finalized_once(db, sender, channel_success):
    svc, uid = sender
    seen = []

    async def send(*args):
        data = args[-1]
        logs = db.query(NotificationLog).all()
        assert len(logs) == 1
        log = logs[0]
        assert log.status == "pending"
        assert log.user_id == uid
        assert data["deep_link"] == f"/notification-history?detailId={log.id}"
        assert log.data["deep_link"] == data["deep_link"]
        # The pre-send commit has ended the write transaction; a separate session
        # can read the same row in PostgreSQL integration runs as well.
        from sqlalchemy.orm import Session
        with Session(bind=db.get_bind()) as reader:
            assert reader.get(NotificationLog, log.id) is not None
        seen.append(log.id)
        return {"success": channel_success, **({} if channel_success else {"error": "unavailable"})}

    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", side_effect=send):
        result = await svc.send_notification(uid, "ai_advice", "睡眠质量下滑", "请查看睡眠变化", data={})
    assert result["success"] == channel_success
    logs = db.query(NotificationLog).all()
    assert [row.id for row in logs] == seen
    assert logs[0].status == ("sent" if channel_success else "failed")
    assert bool(logs[0].sent_at) == channel_success
    assert logs[0].channels[0]["status"] == logs[0].status


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    {"deep_link": "/calendar"}, {"deeplink": "/diet"}, {"screen": "sleep"},
    {"reminder_type": "medication", "medication_id": 12},
])
async def test_live_delivery_keeps_specialized_payload(db, sender, data):
    svc, uid = sender
    send = AsyncMock(return_value={"success": True})
    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", send):
        await svc.send_notification(uid, "reminder", "提醒", "打开查看", data=data)
    assert send.call_args.args[-1] == data


@pytest.mark.asyncio
async def test_delayed_replay_uses_original_id_and_keeps_single_row(db, sender):
    svc, uid = sender
    send = AsyncMock(return_value={"success": True})
    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 3)):
        result = await svc.send_notification(uid, "ai_advice", "睡眠质量下滑", "请查看睡眠变化")
    assert result["reason"] == "delayed_for_quiet_hours"
    original = db.query(NotificationLog).one()
    original_id = original.id
    assert original.status == "delayed"
    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", send):
        result = await svc.flush_delayed_pushes()
    assert result["succeeded"] == 1
    log = db.query(NotificationLog).one()
    assert log.id == original_id
    assert log.status == "sent"
    assert send.call_args.args[-1]["deep_link"] == f"/notification-history?detailId={original_id}"
    assert log.data["deep_link"] == send.call_args.args[-1]["deep_link"]


@pytest.mark.asyncio
async def test_replay_rejects_other_owner_before_sending(db, sender):
    svc, uid = sender
    other = User(name="Other delivery", username="other_delivery", email="other_delivery@example.test", hashed_password="x")
    db.add(other)
    db.commit()
    log = NotificationLog(user_id=other.id, notification_type="ai_advice", channel="multi", title="other", status="pending")
    db.add(log)
    db.commit()
    send = AsyncMock(return_value={"success": True})
    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", send):
        result = await svc.send_notification(uid, "ai_advice", "notice", "body", log_delivery=False, _replay_log_id=log.id)
    assert result == {"success": False, "reason": "invalid_delivery_log"}
    send.assert_not_called()
    assert db.query(NotificationLog).count() == 1
    assert log.status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("text,redacted", [("今晚早点休息", False), ("二甲双胍需要查看", True)])
async def test_saved_originals_never_leave_in_channel_payload(db, sender, text, redacted):
    svc, uid = sender
    send = AsyncMock(return_value={"success": True})
    originals = {"full_title": "原始标题", "full_content": text}
    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", send):
        result = await svc.send_notification(uid, "ai_advice", "健康建议", text, data=originals)
    assert result["success"]
    wire = send.call_args.args[-1]
    assert "full_title" not in wire and "full_content" not in wire
    assert wire["deep_link"].startswith("/notification-history?detailId=")
    if redacted:
        assert "二甲双胍" not in send.call_args.args[-2]
        assert wire["lock_screen_redacted"] is True
    else:
        assert send.call_args.args[-2] == text
        assert "lock_screen_redacted" not in wire
    log = db.query(NotificationLog).one()
    assert log.data["full_content"] == text
    assert originals == {"full_title": "原始标题", "full_content": text}


@pytest.mark.asyncio
async def test_commit_failure_prevents_channel_send(db, sender):
    svc, uid = sender
    send = AsyncMock(return_value={"success": True})
    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", send), \
         patch.object(db, "commit", side_effect=RuntimeError("synthetic unavailable database")):
        with pytest.raises(RuntimeError, match="synthetic unavailable"):
            await svc.send_notification(uid, "reminder", "通知", "查看通知", data={})
    send.assert_not_called()
    db.rollback()
    assert db.query(NotificationLog).count() == 0


@pytest.mark.asyncio
async def test_uncertain_finalization_is_pending_and_is_not_resent(db, sender):
    svc, uid = sender
    send = AsyncMock(return_value={"success": True})
    original_commit = db.commit
    commit_count = 0

    def commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise RuntimeError("synthetic finalization failure")
        return original_commit()

    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", send):
        with patch.object(db, "commit", side_effect=commit):
            with pytest.raises(RuntimeError, match="synthetic finalization"):
                await svc.send_notification(uid, "reminder", "通知", "查看通知")
        db.rollback()
        assert db.query(NotificationLog).one().status == "pending"
        result = await svc.send_notification(uid, "reminder", "通知", "查看通知")
    assert result["reason"] == "dedup"
    assert send.call_count == 1
    assert db.query(NotificationLog).count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled", [True, False])
async def test_rejected_delivery_does_not_create_pending_record(db, sender, disabled):
    svc, uid = sender
    if disabled:
        db.query(UserNotificationSetting).filter_by(user_id=uid).update({"enabled": False})
        db.commit()
    send = AsyncMock(return_value={"success": True})
    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", send):
        result = await svc.send_notification(uid, "reminder", "通知", "查看通知", channels=[])
    assert not result["success"]
    send.assert_not_called()
    assert db.query(NotificationLog).count() == 0


@pytest.mark.parametrize("workout_id,expected", [
    (42, "/workout-detail?id=42"), ("42", "/workout-detail?id=42"),
    (0, "/notification-history?detailId=7"), (True, "/notification-history?detailId=7"),
    ("42&content=private", "/notification-history?detailId=7"),
])
def test_workout_history_route_is_type_bound_and_validated(workout_id, expected):
    assert history_deeplink("workout_analysis", {"workout_id": workout_id}, log_id=7) == expected


@pytest.mark.asyncio
async def test_shared_privacy_guard_saves_original_only_in_owned_log(db, sender):
    svc, uid = sender
    send = AsyncMock(return_value={"success": True})
    with patch("app.services.notification.push_service.get_china_now", return_value=datetime(2026, 10, 18, 13)), \
         patch.object(svc, "_send_ios", send):
        result = await svc.send_notification(uid, "ai_advice", "二甲双胍提示", "二甲双胍需要查看")
    assert result["success"]
    log = db.query(NotificationLog).one()
    assert log.data["full_title"] == "二甲双胍提示"
    assert log.data["full_content"] == "二甲双胍需要查看"
    assert "full_title" not in send.call_args.args[-1]
    assert "full_content" not in send.call_args.args[-1]
    assert "二甲双胍" not in send.call_args.args[-2]


def test_workout_identifier_does_not_override_legacy_screen_destination():
    assert history_deeplink("workout_analysis", {"screen": "alerts", "workout_id": 42}, log_id=7) is None


def test_generic_delivery_bridge_uses_existing_history_surface():
    route = urlsplit(history_deeplink("ai_advice", {}, log_id=7))
    # Old clients know this route and ignore the new selector; newer clients can
    # enter the owned detail after their history screen validates the selector.
    assert route.path == "/notification-history"
    assert parse_qs(route.query) == {"detailId": ["7"]}
    mobile_route = Path(__file__).resolve().parents[2] / "mobile" / "app" / f"{route.path.lstrip('/')}.tsx"
    assert mobile_route.is_file()
