"""Notification Celery beat schedule wiring."""

from celery.schedules import crontab


def test_sleep_reminder_runs_before_default_quiet_hours():
    """系统睡眠提醒应在默认 22:00 静默窗口前发送, 避免 Apple Watch 入睡后打扰."""
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("sleep-reminder")
    assert entry is not None
    assert entry["task"] == "app.tasks.notifications.send_sleep_reminders"
    assert entry["schedule"] == crontab(hour=21, minute=30)
