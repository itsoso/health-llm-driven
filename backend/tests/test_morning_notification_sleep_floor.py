"""Morning notification sleep-floor tests."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import UserNotificationSetting
from app.models.user import User
from app.services.notification.push_scheduler import PushScheduler


def _make_user(db, username: str = "morning_floor_user") -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        name=username,
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_settings(db, user_id: int, **overrides) -> UserNotificationSetting:
    settings = UserNotificationSetting(
        user_id=user_id,
        enabled=True,
        morning_briefing_enabled=True,
        ios_push_enabled=True,
        ios_device_token="apns-token",
        quiet_hours_start="22:00",
        quiet_hours_end="09:00",
        **overrides,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


@pytest.mark.asyncio
async def test_scheduler_does_not_send_historical_8am_morning_briefing_at_8(db):
    """历史 08:00 简报配置不能在 08:00 发送,必须静默到 09:00。"""
    user = _make_user(db, "historical_8am")
    _make_settings(db, user.id, morning_briefing_time="08:00")
    push_service = AsyncMock()

    with patch(
        "app.services.notification.push_scheduler.AISchedulerService"
    ) as scheduler_cls:
        scheduler_cls.return_value.get_morning_briefing.return_value = {
            "greeting": "早安",
            "sections": [{"title": "今日重点"}],
        }
        await PushScheduler()._send_morning_briefings(
            db,
            push_service,
            datetime(2026, 7, 12, 8, 0, 0),
        )

    push_service.send_notification.assert_not_awaited()
    scheduler_cls.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_sends_historical_8am_morning_briefing_at_9(db):
    """历史 08:00 简报配置要在 09:00 睡眠保护结束后补发。"""
    user = _make_user(db, "historical_8am_at_9")
    _make_settings(db, user.id, morning_briefing_time="08:00")
    push_service = AsyncMock()
    push_service.send_notification.return_value = {"success": True}

    with patch(
        "app.services.notification.push_scheduler.AISchedulerService"
    ) as scheduler_cls:
        scheduler_cls.return_value.get_morning_briefing.return_value = {
            "greeting": "早安",
            "sections": [{"title": "今日重点"}],
        }
        await PushScheduler()._send_morning_briefings(
            db,
            push_service,
            datetime(2026, 7, 12, 9, 0, 0),
        )

    push_service.send_notification.assert_awaited_once()
    scheduler_cls.assert_called_once()


def test_notification_settings_default_morning_time_is_9(client, db):
    """新用户默认早间简报时间不能落在 07:00/08:00 睡眠窗口。"""
    from app.services.auth import auth_service

    user = _make_user(db, "settings_default_9")
    token = auth_service.create_access_token({"sub": str(user.id)})

    response = client.get(
        "/api/v1/notification/settings",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["morning_briefing_time"] == "09:00"
    assert body["quiet_hours_end"] == "09:00"


def test_notification_settings_normalizes_8am_update_to_9(client, db):
    """写入 08:00 也要归一到 09:00,避免后续调度在睡眠窗口命中。"""
    from app.services.auth import auth_service

    user = _make_user(db, "settings_update_8_to_9")
    token = auth_service.create_access_token({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.put(
        "/api/v1/notification/settings",
        json={"morning_briefing_time": "08:00", "quiet_hours_end": "08:00"},
        headers=headers,
    )

    assert response.status_code == 200
    refreshed = client.get("/api/v1/notification/settings", headers=headers)
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["morning_briefing_time"] == "09:00"
    assert body["quiet_hours_end"] == "09:00"
