import logging
from datetime import datetime, timedelta

import pytest

from app.models.smart_reminder import SmartReminder
from app.services.notification.push_service import PushService
from app.services.reminder_service import ReminderService
from app.utils.timezone import CHINA_TIMEZONE


@pytest.mark.asyncio
async def test_fired_reminder_log_does_not_expose_title_or_payload(
    db, auth_user_and_headers, monkeypatch, caplog,
):
    user, _ = auth_user_and_headers
    reminder = SmartReminder(
        user_id=user.id,
        title="服用测试药A",
        message="服用测试药A 10mg",
        remind_at=datetime.now(CHINA_TIMEZONE) + timedelta(minutes=1),
        status="pending",
        priority="normal",
    )
    db.add(reminder)
    db.commit()

    async def fake_send(self, **kwargs):
        return {"success": True}

    monkeypatch.setattr(PushService, "send_notification", fake_send)
    with caplog.at_level(logging.INFO):
        await ReminderService(db).fire_reminder(reminder)

    assert reminder.status == "fired"
    assert "服用测试药A" not in caplog.text
    assert "10mg" not in caplog.text
