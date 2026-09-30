"""PushService severity contract for health_alert: never silently drop, always loud.

Root cause (2026-09-30): send_notification defaulted severity="info" and
_severity_rank mapped unknown strings to 0, so a health_alert producer that forgot
``severity=`` (or misspelled it) ranked below the default H1-B threshold ("warning")
and was dropped with only an INFO line. Garmin-sync Safety Guardian pushes and
AnomalyDetectionService.send_alerts were lost from 2026-05-01 to 2026-09-30.

Decision under test: a missing/unknown health_alert severity is a producer bug →
ERROR log (with rule_id, without health payload) and fail-open at "warning" — the
default threshold, so the default user still receives it; non-critical, so
quiet hours / 09:00 floor / standard dedup still apply. Explicit valid tiers are
honoured as-is (an explicit "info" is still filtered).

These tests drive the real gating path (settings, threshold, quiet hours, delayed
queue, flush); only the APNs transport is stubbed.
"""
import asyncio
import logging
from datetime import datetime
from unittest.mock import patch

from app.agents.safety_guardian.schema import Severity
from app.models.notification import NotificationLog, NotificationStatus, UserNotificationSetting
from app.models.user import User
from app.services.notification.push_service import PushService

PUSH_LOGGER = "app.services.notification.push_service"
NOW = "app.services.notification.push_service.get_china_now"
DAYTIME = datetime(2026, 9, 30, 14, 0)
NIGHT = datetime(2026, 9, 30, 23, 30)
BEFORE_MORNING_FLOOR = datetime(2026, 9, 30, 8, 0)
AFTER_MORNING_FLOOR = datetime(2026, 9, 30, 9, 30)
FILTERED = "通知已禁用/低于阈值/规则已静音"


class _UnconfiguredTelegram:
    configured = False


def _user(db, **settings) -> int:
    user = User(username="sev", email="sev@test.local", name="sev", hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserNotificationSetting(
        user_id=user.id,
        enabled=True,
        health_alert_enabled=True,
        reminder_enabled=True,
        ai_advice_enabled=True,
        ios_push_enabled=True,
        ios_device_token="fake-token",
        wechat_enabled=False,
        **settings,
    ))
    db.commit()
    return user.id


def _send(db, **kwargs) -> dict:
    kwargs.setdefault("title", "血氧告警")
    kwargs.setdefault("content", "夜间血氧最低 86%")
    return asyncio.run(PushService(db).send_notification(**kwargs))


def _errors(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


def _delayed_rows(db, user_id) -> list[NotificationLog]:
    return db.query(NotificationLog).filter(
        NotificationLog.user_id == user_id,
        NotificationLog.status == NotificationStatus.DELAYED.value,
    ).all()


class TestHealthAlertSeverityFailOpen:
    @patch(NOW, return_value=DAYTIME)
    def test_missing_severity_is_delivered_and_logged_as_error(self, _now, db, caplog):
        user_id = _user(db)  # default alert_severity_threshold = "warning"
        with patch.object(PushService, "_send_ios", return_value={"success": True}) as ios, \
                caplog.at_level(logging.ERROR, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="health_alert",
                data={"rule_id": "vitals.spo2_low"}, channels=["ios_apns"],
            )

        assert result["success"] is True, result
        ios.assert_called_once()
        errors = _errors(caplog)
        assert len(errors) == 1, errors
        assert "health_alert" in errors[0] and "vitals.spo2_low" in errors[0]
        assert "86%" not in errors[0], "log must not carry the health payload"

    @patch(NOW, return_value=DAYTIME)
    def test_misspelled_severity_is_delivered_and_logged_as_error(self, _now, db, caplog):
        user_id = _user(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}) as ios, \
                caplog.at_level(logging.ERROR, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="health_alert", severity="critcal",
                data={"rule_id": "cgm.hypo"}, channels=["ios_apns"],
            )

        assert result["success"] is True, result
        ios.assert_called_once()
        errors = _errors(caplog)
        assert len(errors) == 1 and "critcal" in errors[0] and "cgm.hypo" in errors[0]

    @patch(NOW, return_value=DAYTIME)
    def test_text_passed_as_severity_is_not_logged(self, _now, db, caplog):
        user_id = _user(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}), \
                caplog.at_level(logging.ERROR, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="health_alert", severity="夜间血氧最低 86%",
                data={"rule_id": "vitals.spo2_low"}, channels=["ios_apns"],
            )

        assert result["success"] is True, result
        (error,) = _errors(caplog)
        assert "86%" not in error and "血氧" not in error

    @patch(NOW, return_value=DAYTIME)
    def test_enum_instead_of_label_fails_open_instead_of_raising(self, _now, db, caplog):
        """severity=alert.severity (IntEnum) instead of .label used to raise AttributeError."""
        user_id = _user(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}) as ios, \
                caplog.at_level(logging.ERROR, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="health_alert", severity=Severity.CRITICAL,
                data={"rule_id": "vitals.bp_crisis"}, channels=["ios_apns"],
            )

        assert result["success"] is True, result
        ios.assert_called_once()
        assert len(_errors(caplog)) == 1

    @patch(NOW, return_value=NIGHT)
    def test_padded_mixed_case_critical_is_normalised_not_dropped(self, _now, db, caplog):
        """" Critical " must still punch through quiet hours as critical (no fallback)."""
        user_id = _user(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}) as ios, \
                caplog.at_level(logging.WARNING, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="health_alert", severity=" Critical ",
                data={"rule_id": "vitals.bp_crisis"}, channels=["ios_apns"],
            )

        assert result["success"] is True, result
        ios.assert_called_once()
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []

    @patch(NOW, return_value=NIGHT)
    def test_fallback_tier_is_non_critical_so_quiet_hours_still_apply(self, _now, db):
        user_id = _user(db)
        result = _send(
            db, user_id=user_id, notification_type="health_alert",
            data={"rule_id": "vitals.spo2_low"},
        )

        assert result["reason"] == "delayed_for_quiet_hours", result
        (row,) = _delayed_rows(db, user_id)
        assert row.data["severity"] == "warning"

    @patch(NOW, return_value=DAYTIME)
    def test_fallback_honours_explicit_critical_only_threshold_but_stays_loud(self, _now, db, caplog):
        """Deliberate trade-off: an unknown tier is not escalated past a user's explicit
        critical-only preference; the ERROR line is what surfaces the producer bug."""
        user_id = _user(db, alert_severity_threshold="critical")
        with caplog.at_level(logging.ERROR, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="health_alert",
                data={"rule_id": "vitals.spo2_low"}, channels=["ios_apns"],
            )

        assert result == {"success": False, "reason": FILTERED}
        assert len(_errors(caplog)) == 1

    @patch(NOW, return_value=DAYTIME)
    def test_explicit_low_tier_is_respected_and_not_an_error(self, _now, db, caplog):
        user_id = _user(db)
        with caplog.at_level(logging.WARNING, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="health_alert", severity="info",
                data={"rule_id": "vitals.minor"}, channels=["ios_apns"],
            )

        assert result == {"success": False, "reason": FILTERED}
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []

    @patch(NOW, return_value=DAYTIME)
    def test_other_types_keep_the_info_default_without_noise(self, _now, db, caplog):
        user_id = _user(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}), \
                caplog.at_level(logging.WARNING, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="reminder",
                title="💧 喝水提醒", content="记得喝水", channels=["ios_apns"],
            )

        assert result["success"] is True, result
        assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []

    @patch(NOW, return_value=DAYTIME)
    def test_other_types_warn_on_unknown_severity(self, _now, db, caplog):
        user_id = _user(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}), \
                caplog.at_level(logging.WARNING, logger=PUSH_LOGGER):
            result = _send(
                db, user_id=user_id, notification_type="ai_advice", severity="urgent",
                title="今天适合轻松活动", content="恢复度一般", channels=["ios_apns"],
            )

        assert result["success"] is True, result
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1 and "urgent" in warnings[0].getMessage()
        assert _errors(caplog) == []


class TestDelayedReplaySeverity:
    """flush_delayed_pushes replays data["severity"]; it must be the tier that was gated."""

    def test_delayed_row_keeps_gating_tier_over_producer_label(self, db, monkeypatch):
        monkeypatch.setattr(PushService, "telegram", property(lambda self: _UnconfiguredTelegram()))
        user_id = _user(db)
        with patch(NOW, return_value=BEFORE_MORNING_FLOOR):
            result = _send(
                db, user_id=user_id, notification_type="health_alert", severity="critical",
                # producer label disagrees with the gating tier
                data={"rule_id": "vitals.spo2_critical", "severity": "info"},
            )
        assert result["reason"] == "delayed_for_quiet_hours", result
        (row,) = _delayed_rows(db, user_id)
        assert row.data["severity"] == "critical"

        with patch(NOW, return_value=AFTER_MORNING_FLOOR), \
                patch.object(PushService, "_send_ios", return_value={"success": True}) as ios:
            flushed = asyncio.run(PushService(db).flush_delayed_pushes())

        assert flushed["succeeded"] == 1, flushed
        ios.assert_called_once()
        db.refresh(row)
        assert row.status == NotificationStatus.SENT.value

    def test_legacy_row_without_severity_is_not_silently_dropped_on_replay(self, db, monkeypatch, caplog):
        monkeypatch.setattr(PushService, "telegram", property(lambda self: _UnconfiguredTelegram()))
        user_id = _user(db)
        row = NotificationLog(
            user_id=user_id,
            notification_type="health_alert",
            channel="multi",
            title="⚠️ 血氧偏低",
            content="夜间血氧最低 86%",
            data={"rule_id": "vitals.spo2_low"},  # written before severity was persisted
            status=NotificationStatus.DELAYED.value,
            scheduled_at=datetime(2026, 9, 30, 9, 0),
        )
        db.add(row)
        db.commit()

        with patch(NOW, return_value=AFTER_MORNING_FLOOR), \
                patch.object(PushService, "_send_ios", return_value={"success": True}) as ios, \
                caplog.at_level(logging.ERROR, logger=PUSH_LOGGER):
            flushed = asyncio.run(PushService(db).flush_delayed_pushes())

        assert flushed["succeeded"] == 1, flushed
        ios.assert_called_once()
        errors = _errors(caplog)
        assert len(errors) == 1 and "vitals.spo2_low" in errors[0]
        db.refresh(row)
        assert row.status == NotificationStatus.SENT.value
