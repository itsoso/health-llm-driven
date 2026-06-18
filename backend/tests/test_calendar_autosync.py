"""日历定时同步任务注册 + beat 调度(不跑真 DB,只验装配)。"""
def test_task_importable_and_registered():
    from app.tasks.calendar_tasks import sync_all_calendars  # noqa
    from app.celery_app import celery_app
    assert "app.tasks.calendar_tasks.sync_all_calendars" in celery_app.tasks


def test_beat_schedule_has_calendar_sync():
    from app.celery_app import celery_app
    entry = celery_app.conf.beat_schedule.get("sync-all-calendars")
    assert entry is not None
    assert entry["task"] == "app.tasks.calendar_tasks.sync_all_calendars"
