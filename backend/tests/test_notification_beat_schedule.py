"""Notification Celery beat schedule wiring."""

from celery.schedules import crontab


def test_sleep_reminder_runs_before_default_quiet_hours():
    """系统睡眠提醒应在默认 22:00 静默窗口前发送, 避免 Apple Watch 入睡后打扰."""
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("sleep-reminder")
    assert entry is not None
    assert entry["task"] == "app.tasks.notifications.send_sleep_reminders"
    assert entry["schedule"] == crontab(hour=21, minute=30)


def test_open_loop_manager_runs_after_default_quiet_hours():
    """主动循环推送应在默认 22:00-09:00 静默结束后再扫描。"""
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("open-loop-manager")
    assert entry is not None
    assert entry["task"] == "app.tasks.open_loop_manager.run_open_loop_check"
    assert entry["schedule"] == crontab(hour=9, minute=15)


def test_user_visible_morning_pushes_do_not_run_before_quiet_hours_end():
    """7 点和 8 点附近不启动用户可见推送任务,避免影响睡眠。"""
    from app.celery_app import celery_app

    expected = {
        "plan-morning-reminder": {
            "task": "app.tasks.notifications.send_plan_morning_reminder",
            "schedule": crontab(hour=9, minute=10),
        },
        "trend-morning-push": {
            "task": "app.tasks.notifications.send_trend_morning_push",
            "schedule": crontab(hour=9, minute=25),
        },
        "morning-health-summary": {
            "task": "app.tasks.notifications.send_morning_health_summary",
            "schedule": crontab(hour=9, minute=30),
        },
        "monthly-report-generate": {
            "task": "app.tasks.monthly_report.generate_previous_month_reports",
            "schedule": crontab(hour=9, minute=12, day_of_month=1),
        },
    }

    for name, expectation in expected.items():
        entry = celery_app.conf.beat_schedule.get(name)
        assert entry is not None
        assert entry["task"] == expectation["task"]
        assert entry["schedule"] == expectation["schedule"]
