"""Notification Celery beat schedule wiring."""

from celery.schedules import crontab


def test_sleep_reminder_runs_before_default_quiet_hours():
    """系统睡眠提醒应在默认 22:00 静默窗口前发送, 避免 Apple Watch 入睡后打扰."""
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("sleep-reminder")
    assert entry is not None
    assert entry["task"] == "app.tasks.notifications.send_sleep_reminders"
    assert entry["schedule"] == crontab(hour=21, minute=30)


def test_user_visible_morning_pushes_are_not_scheduled_before_quiet_hours_end():
    """09:00 前是睡眠保护窗口, 面向用户的早晨推送不能由 beat 直接触发."""
    from app.celery_app import celery_app

    protected_entries = {
        "plan-morning-reminder": "app.tasks.notifications.send_plan_morning_reminder",
        "trend-morning-push": "app.tasks.notifications.send_trend_morning_push",
        "morning-health-summary": "app.tasks.notifications.send_morning_health_summary",
        "daily-briefing-message": "app.tasks.notifications.generate_daily_briefing_message",
        "open-loop-manager": "app.tasks.open_loop_manager.run_open_loop_check",
        "monthly-report-generate": "app.tasks.monthly_report.generate_previous_month_reports",
    }

    for name, task in protected_entries.items():
        entry = celery_app.conf.beat_schedule.get(name)
        assert entry is not None
        assert entry["task"] == task
        schedule = entry["schedule"]
        assert schedule.hour == {9}
