"""Safety Guardian HIGH/CRITICAL alerts must actually reach APNs — and logs must say what happened.

evaluate_and_push_safety is the only post-Garmin-sync safety push (the inline one in
tasks/garmin_sync.py was removed 2026-09-30), and daily_anomaly_check's scheduled
Safety Guardian pass is the nightly one. Both used to log "已推送" regardless of what
PushService returned, which is how the 2026-05-01~09-30 silent drop hid.

These tests run the real task bodies with a real PushService: only the twin build /
Safety evaluation (fake report), the APNs transport (``_send_ios``) and the clock are
stubbed; Telegram is unconfigured; default alert_severity_threshold.
"""
import logging
from contextlib import AbstractContextManager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.safety_guardian.schema import Alert, SafetyReport, Severity
from app.models.notification import NotificationLog, UserNotificationSetting
from app.services.notification.push_service import PushService

TASK_LOGGER = "app.tasks.notifications"
DAYTIME = datetime(2026, 9, 30, 14, 0)


def _alert(severity: Severity, rule_id: str) -> Alert:
    return Alert(
        rule_id=rule_id,
        category="vitals",
        severity=severity,
        title="夜间血氧过低",
        message="夜间血氧最低 86%，低于安全阈值。",
    )


ALERTS = [
    _alert(Severity.HIGH, "vitals.bp_stage2"),
    _alert(Severity.CRITICAL, "vitals.spo2_critical"),
]


@pytest.fixture
def harness(db, monkeypatch):
    """Real PushService over the test DB; returns the APNs stub (success by default)."""
    from app.agents import safety_guardian
    from app.services.notification import push_service as push_module
    from app.tasks import notifications
    from app.twin import builder as twin_builder
    from tests.test_garmin_sync import _create_garmin_credential

    credential = _create_garmin_credential(db, user_id=1)
    db.add(UserNotificationSetting(
        user_id=credential.user_id,
        enabled=True,
        ios_push_enabled=True,
        ios_device_token="fake-token",
        wechat_enabled=False,
    ))
    db.commit()

    class DbContext(AbstractContextManager):
        def __enter__(self):
            return db

        def __exit__(self, *_args):
            return False

    fake_twin = SimpleNamespace(meta=SimpleNamespace(data_sources=[]))
    monkeypatch.setattr(notifications, "SessionLocal", lambda: DbContext())
    monkeypatch.setattr(twin_builder, "build_twin", lambda *_args, **_kwargs: fake_twin)
    monkeypatch.setattr(
        safety_guardian, "evaluate_safety", lambda _twin: SafetyReport(user_id=1, alerts=list(ALERTS)),
    )
    monkeypatch.setattr(push_module, "get_china_now", lambda: DAYTIME)
    monkeypatch.setattr(PushService, "telegram", property(lambda self: SimpleNamespace(configured=False)))
    ios = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(PushService, "_send_ios", ios)
    return ios


def _sent_rule_ids(ios) -> set[str]:
    return {c.args[-1]["rule_id"] for c in ios.await_args_list}


def _errors(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


class TestRealtimeSafetyPush:
    def test_high_and_critical_both_reach_apns_at_default_threshold(self, db, harness, caplog):
        from app.tasks import notifications

        with caplog.at_level(logging.INFO, logger=TASK_LOGGER):
            notifications.evaluate_and_push_safety.run(1)

        assert harness.await_count == 2
        assert _sent_rule_ids(harness) == {"vitals.bp_stage2", "vitals.spo2_critical"}
        sent = db.query(NotificationLog).filter(
            NotificationLog.notification_type == "health_alert", NotificationLog.status == "sent",
        ).count()
        assert sent == 2
        assert _errors(caplog) == []
        assert "送达 2/2" in caplog.text

    def test_apns_failure_is_logged_as_error_not_as_pushed(self, harness, caplog):
        from app.tasks import notifications

        harness.return_value = {"success": False, "error": "BadDeviceToken"}
        with caplog.at_level(logging.INFO, logger=TASK_LOGGER):
            notifications.evaluate_and_push_safety.run(1)

        (error,) = _errors(caplog)
        assert "送达 0/2" in error and "失败 2" in error
        assert "86%" not in error, "log must not carry the health payload"


class TestScheduledSafetyPush:
    @pytest.fixture(autouse=True)
    def _no_anomalies(self, monkeypatch):
        from app.services import anomaly_detection_service

        monkeypatch.setattr(
            anomaly_detection_service.AnomalyDetectionService,
            "detect_anomalies",
            lambda *_args, **_kwargs: [],
        )

    def test_logs_real_delivery_count(self, harness, caplog):
        from app.tasks import notifications

        with caplog.at_level(logging.INFO, logger=TASK_LOGGER):
            notifications.daily_anomaly_check.run()

        assert harness.await_count == 2
        assert "送达 2/2" in caplog.text
        assert _errors(caplog) == []

    def test_failed_delivery_is_not_logged_as_pushed(self, harness, caplog):
        from app.tasks import notifications

        harness.return_value = {"success": False, "error": "BadDeviceToken"}
        with caplog.at_level(logging.INFO, logger=TASK_LOGGER):
            notifications.daily_anomaly_check.run()

        assert "已推送告警" not in caplog.text
        (error,) = _errors(caplog)
        assert "送达 0/2" in error and "失败 2" in error

    def test_suppressed_by_dedup_is_reported_as_such(self, harness, caplog):
        from app.tasks import notifications

        notifications.daily_anomaly_check.run()  # first pass delivers both
        harness.reset_mock()
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=TASK_LOGGER):
            notifications.daily_anomaly_check.run()

        assert harness.await_count == 0
        assert "送达 0/2" in caplog.text and "dedup" in caplog.text
        assert _errors(caplog) == []
