"""Post-sync Safety Guardian pushes go through evaluate_and_push_safety only.

tasks/garmin_sync.py used to push HIGH+ alerts inline. From 2026-05-01 to
2026-09-30 that push omitted ``severity=`` (implicit "info" < default threshold) and
was dropped while logging "已推送". Fixing it would have made it win the rule_id
dedup race against notifications.evaluate_and_push_safety — which carries
rule-specific deep links — so the inline push was removed (2026-09-30 safety-gate
review). evaluate_and_push_safety is therefore the only post-sync safety push, so the
sync dispatches it directly (not chained behind the 120s briefing task, whose hard
kill would skip it) and a failed dispatch is an ERROR. These tests run the real task
body with a real PushService (only Garmin I/O, the twin build and the APNs transport
are stubbed).
"""
import logging
from contextlib import AbstractContextManager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agents.safety_guardian.schema import Alert, Severity
from app.models.notification import NotificationLog, UserNotificationSetting
from app.services.notification.push_service import PushService

TASK_LOGGER = "app.tasks.garmin_sync"
DAYTIME = datetime(2026, 9, 30, 14, 0)


def _alert(severity: Severity, rule_id: str = "vitals.spo2_critical") -> Alert:
    return Alert(
        rule_id=rule_id,
        category="vitals",
        severity=severity,
        title="夜间血氧过低",
        message="夜间血氧最低 86%，低于安全阈值。",
    )


def _run_sync_with_safety_alerts(
    db, monkeypatch, *, alerts, now, safety_delay=None, briefing_delay=None, **settings
):
    """Run sync_user_garmin_data to completion; return (APNs stub, briefing calls, safety calls)."""
    from app.agents import safety_guardian
    from app.services import agent_loop, anomaly_detection_service, workout_sync
    from app.services import auth as auth_service_module
    from app.services.data_collection import garmin_connect
    from app.services.notification import push_service as push_module
    from app.tasks import garmin_sync as garmin_task
    from app.tasks import notifications
    from app.twin import builder as twin_builder
    from app.twin import cache as twin_cache
    from app import scheduler
    from tests.test_garmin_sync import _create_garmin_credential

    credential = _create_garmin_credential(db, user_id=1)
    db.add(UserNotificationSetting(
        user_id=credential.user_id,
        enabled=True,
        ios_push_enabled=True,
        ios_device_token="fake-token",
        wechat_enabled=False,
        **settings,
    ))
    db.commit()

    class DbContext(AbstractContextManager):
        def __enter__(self):
            return db

        def __exit__(self, *_args):
            return False

    class FakeGarminService:
        def __init__(self, *_args, **_kwargs):
            self.client = object()
            self._authenticated = True

        def sync_date_range(self, *_args, **_kwargs):
            return {"success_count": 1, "error_count": 0, "no_data_count": 0}

    class FakeWorkoutService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def sync_activities(self, *_args, **_kwargs):
            return {"synced_count": 0}

    async def no_agent_action(*_args, **_kwargs):
        return {"action": "none"}

    monkeypatch.setattr(garmin_task, "SessionLocal", lambda: DbContext())
    monkeypatch.setattr(garmin_connect, "GarminConnectService", FakeGarminService)
    monkeypatch.setattr(workout_sync, "WorkoutSyncService", FakeWorkoutService)
    monkeypatch.setattr(scheduler, "_update_vo2max_from_workouts", lambda *_args: None)
    monkeypatch.setattr(twin_cache, "invalidate_twin", lambda *_args: None)
    monkeypatch.setattr(
        anomaly_detection_service.AnomalyDetectionService,
        "detect_anomalies",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(twin_builder, "build_twin", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(safety_guardian, "evaluate_safety", lambda _twin: SimpleNamespace(alerts=alerts))
    monkeypatch.setattr(agent_loop, "post_sync_reasoning", no_agent_action)
    monkeypatch.setattr(
        auth_service_module.garmin_credential_service,
        "update_sync_status",
        lambda *_args, **_kwargs: True,
    )
    briefing_calls, safety_calls = [], []
    monkeypatch.setattr(
        notifications.regenerate_briefing_for_user, "delay",
        briefing_delay or (lambda *args: briefing_calls.append(args)),
    )
    monkeypatch.setattr(
        notifications.evaluate_and_push_safety, "delay",
        safety_delay or (lambda *args: safety_calls.append(args)),
    )

    monkeypatch.setattr(push_module, "get_china_now", lambda: now)
    monkeypatch.setattr(PushService, "telegram", property(lambda self: SimpleNamespace(configured=False)))
    ios = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(PushService, "_send_ios", ios)

    result = garmin_task.sync_user_garmin_data.run(credential.user_id, days=1)
    assert result["status"] == "success", result
    return ios, briefing_calls, safety_calls


def test_sync_does_not_push_safety_alerts_inline(db, monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger=TASK_LOGGER):
        ios, _, _ = _run_sync_with_safety_alerts(
            db, monkeypatch, alerts=[_alert(Severity.CRITICAL)], now=DAYTIME,
        )

    assert ios.await_count == 0
    assert db.query(NotificationLog).filter(NotificationLog.notification_type == "health_alert").count() == 0
    assert "已推送" not in caplog.text


def test_sync_dispatches_the_safety_push_producer_directly(db, monkeypatch):
    """Not chained behind regenerate_briefing_for_user (time_limit=120): a hard kill of
    the briefing task must not be able to skip the only post-sync safety push."""
    _, briefing_calls, safety_calls = _run_sync_with_safety_alerts(
        db, monkeypatch, alerts=[_alert(Severity.CRITICAL)], now=DAYTIME,
    )

    assert safety_calls == [(1,)]
    assert briefing_calls == [(1,)]


def test_briefing_task_no_longer_chains_the_safety_push(monkeypatch):
    """Single dispatcher: a second chained dispatch would race the sync's own dispatch
    through the rule_id dedup (two workers can both pass the check)."""
    from app.tasks import notifications

    safety_calls = []
    monkeypatch.setattr(notifications, "_generate_daily_briefing_for_user", lambda *_args: None)
    monkeypatch.setattr(notifications.evaluate_and_push_safety, "delay", lambda *args: safety_calls.append(args))

    notifications.regenerate_briefing_for_user.run(7)

    assert safety_calls == []


def test_failed_safety_dispatch_is_an_error_and_does_not_block_the_briefing(db, monkeypatch, caplog):
    def broker_down(*_args):
        raise ConnectionError("broker unreachable")

    with caplog.at_level(logging.INFO, logger=TASK_LOGGER):
        _, briefing_calls, _ = _run_sync_with_safety_alerts(
            db, monkeypatch, alerts=[_alert(Severity.CRITICAL)], now=DAYTIME, safety_delay=broker_down,
        )

    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and "evaluate_and_push_safety" in errors[0], errors
    assert briefing_calls == [(1,)]


def test_failed_briefing_dispatch_does_not_block_the_safety_dispatch(db, monkeypatch):
    def broker_down(*_args):
        raise ConnectionError("broker unreachable")

    _, _, safety_calls = _run_sync_with_safety_alerts(
        db, monkeypatch, alerts=[_alert(Severity.CRITICAL)], now=DAYTIME, briefing_delay=broker_down,
    )

    assert safety_calls == [(1,)]
