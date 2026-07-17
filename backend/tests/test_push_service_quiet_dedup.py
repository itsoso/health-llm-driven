"""PushService quiet-hours severity 穿透 + dedup 窗口测试."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.notification import (
    NotificationLog,
    NotificationStatus,
    UserNotificationSetting,
)
from app.models.user import User
from app.services.notification.push_service import PushService


def _make_user(db, username: str = "tester") -> int:
    u = User(
        username=username,
        email=f"{username}@test.local",
        name=username,
        hashed_password="x",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u.id


def _make_settings(
    db,
    user_id: int,
    *,
    enabled: bool = True,
    quiet_start: str = "22:00",
    quiet_end: str = "09:00",
    ios_token: str = "fake-token",
) -> UserNotificationSetting:
    s = UserNotificationSetting(
        user_id=user_id,
        enabled=enabled,
        morning_briefing_enabled=True,
        reminder_enabled=True,
        health_alert_enabled=True,
        ai_advice_enabled=True,
        quiet_hours_start=quiet_start,
        quiet_hours_end=quiet_end,
        ios_push_enabled=True,
        ios_device_token=ios_token,
        wechat_enabled=False,
    )
    db.add(s)
    db.commit()
    return s


class TestQuietHoursSeverity:
    """quiet_hours 策略 (2026-05-30 反转 2026-05-11): critical 穿透静默立即推, 其余延迟."""

    @patch("app.services.notification.push_service.get_china_now")
    def test_medium_alert_suppressed_at_night(self, mock_now, db):
        """medium 在静默时段不再立刻推, 进 delayed 队列 (走 send_notification 路径)."""
        mock_now.return_value = datetime(2026, 5, 1, 23, 30)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        svc = PushService(db)
        # 入口 can_send 不再检查 quiet_hours, 由 send_notification 顶层延迟; 这里 can_send 应通过.
        assert svc.can_send_notification(
            user_id, "health_alert", severity="medium"
        ) is True

        result = asyncio.run(svc.send_notification(
            user_id=user_id,
            notification_type="health_alert",
            title="medium 告警",
            content="x",
            severity="medium",
            data={"rule_id": "test.medium"},
        ))
        assert result["success"] is False
        assert result["reason"] == "delayed_for_quiet_hours"

    @patch("app.services.notification.push_service.get_china_now")
    def test_high_alert_suppressed_at_night(self, mock_now, db):
        """HIGH 级别也走 delayed 队列, 不再"被丢弃" — 静默时段后会自动 fire."""
        mock_now.return_value = datetime(2026, 5, 1, 23, 30)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        svc = PushService(db)
        assert svc.can_send_notification(
            user_id, "health_alert", severity="high"
        ) is True

        result = asyncio.run(svc.send_notification(
            user_id=user_id,
            notification_type="health_alert",
            title="high 告警",
            content="x",
            severity="high",
            data={"rule_id": "test.high"},
        ))
        assert result["success"] is False
        assert result["reason"] == "delayed_for_quiet_hours"

    @patch("app.services.notification.push_service.get_china_now")
    def test_critical_alert_punches_through_at_night(self, mock_now, db):
        """critical 穿透静默时段立即推送 (2026-05-30 反转"严格不打扰").

        致命药物交互 / 急性阈值不应压到早上 —— 原计划的"紧急联系人穿透"从未落地.
        """
        mock_now.return_value = datetime(2026, 5, 1, 23, 30)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        svc = PushService(db)
        assert svc.can_send_notification(
            user_id, "health_alert", severity="critical"
        ) is True

        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="critical 告警",
                content="x",
                severity="critical",
                data={"rule_id": "test.critical"},
                channels=["ios_apns"],
            ))
        # 立即发送, 不进延迟队列
        assert result.get("success") is True
        assert result.get("reason") != "delayed_for_quiet_hours"
        delayed = (
            db.query(NotificationLog)
            .filter(
                NotificationLog.user_id == user_id,
                NotificationLog.status == NotificationStatus.DELAYED.value,
            )
            .count()
        )
        assert delayed == 0

    @patch("app.services.notification.push_service.get_china_now")
    def test_delayed_log_persists_severity_for_flush(self, mock_now, db):
        """delayed log 必须把 severity 落进 data —— flush_delayed_pushes 靠它回放.

        severity 是 send_notification 的独立入参, 调用方通常不放进 data
        (见 tasks/notifications.py 实时安全评估: data 只有 rule_id/deep_link).
        _log_notification_delayed 负责注入; 若哪天丢了这行, flush 会把 critical
        读成 "info" 并按 info 回放 → 静默降级 (under-alarm).
        """
        # 08:00 在晨间地板 (09:00) 前 → 即便 critical 也被强制进 delayed 队列
        mock_now.return_value = datetime(2026, 5, 1, 8, 0)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        svc = PushService(db)

        result = asyncio.run(svc.send_notification(
            user_id=user_id,
            notification_type="health_alert",
            title="critical 告警",
            content="x",
            severity="critical",
            data={"rule_id": "test.critical_floor"},  # 注意: 调用方没放 severity
        ))
        assert result["success"] is False
        assert result["reason"] == "delayed_for_quiet_hours"

        log = (
            db.query(NotificationLog)
            .filter(
                NotificationLog.user_id == user_id,
                NotificationLog.status == NotificationStatus.DELAYED.value,
            )
            .one()
        )
        assert (log.data or {}).get("severity") == "critical", (
            "delayed log 丢了 severity → flush 会把 critical 当 info 回放"
        )

    @patch("app.services.notification.push_service.get_china_now")
    def test_default_quiet_hours_covers_0830(self, mock_now, db):
        """默认 22:00–09:00：08:30 仍算夜间，09:00 算白天."""
        user_id = _make_user(db)
        _make_settings(db, user_id)  # 用默认 22:00–09:00
        svc = PushService(db)

        mock_now.return_value = datetime(2026, 5, 1, 8, 30)
        assert svc.is_quiet_hours(user_id) is True

        mock_now.return_value = datetime(2026, 5, 1, 9, 0)
        assert svc.is_quiet_hours(user_id) is False

    @patch("app.services.notification.push_service.get_china_now")
    def test_daytime_non_critical_passes(self, mock_now, db):
        mock_now.return_value = datetime(2026, 5, 1, 14, 0)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        svc = PushService(db)
        assert svc.can_send_notification(
            user_id, "health_alert", severity="medium"
        ) is True


class TestDedup:
    """dedup_window_hours：同 (user, type, title) 窗口内已发就跳过."""

    @patch("app.services.notification.push_service.get_china_now")
    def test_dedup_hit_skips_send(self, mock_now, db):
        mock_now.return_value = datetime(2026, 5, 1, 14, 0)
        user_id = _make_user(db)
        _make_settings(db, user_id)

        # 窗口内有一条成功发送记录
        db.add(NotificationLog(
            user_id=user_id,
            notification_type="health_alert",
            channel="ios_apns",
            title="⚠️ BP Spike",
            content="earlier",
            status=NotificationStatus.SENT.value,
            sent_at=datetime(2026, 5, 1, 10, 0),
        ))
        db.commit()

        svc = PushService(db)
        result = asyncio.run(svc.send_notification(
            user_id=user_id,
            notification_type="health_alert",
            title="⚠️ BP Spike",
            content="again",
            severity="high",
        ))
        assert result["success"] is False
        assert result["reason"] == "dedup"

    @patch("app.services.notification.push_service.get_china_now")
    def test_dedup_outside_window_passes(self, mock_now, db):
        mock_now.return_value = datetime(2026, 5, 1, 20, 0)
        user_id = _make_user(db)
        _make_settings(db, user_id)

        # 10 小时前发送过 — 显式使用 6h 窗口, 应已过期
        db.add(NotificationLog(
            user_id=user_id,
            notification_type="health_alert",
            channel="ios_apns",
            title="⚠️ BP Spike",
            content="earlier",
            status=NotificationStatus.SENT.value,
            sent_at=datetime(2026, 5, 1, 10, 0),
        ))
        db.commit()

        svc = PushService(db)
        # 让下游 channel 路径不真发：没有 wechat_openid / telegram，ios 会尝试发
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ BP Spike",
                content="later",
                severity="high",
                dedup_window_hours=6,
                channels=["ios_apns"],
            ))
        assert result.get("reason") != "dedup"

    @patch("app.services.notification.push_service.get_china_now")
    def test_dedup_zero_disables(self, mock_now, db):
        mock_now.return_value = datetime(2026, 5, 1, 14, 0)
        user_id = _make_user(db)
        _make_settings(db, user_id)

        db.add(NotificationLog(
            user_id=user_id,
            notification_type="health_alert",
            channel="ios_apns",
            title="⚠️ BP Spike",
            content="earlier",
            status=NotificationStatus.SENT.value,
            sent_at=datetime(2026, 5, 1, 13, 30),
        ))
        db.commit()

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ BP Spike",
                content="again",
                severity="high",
                dedup_window_hours=0,
                channels=["ios_apns"],
            ))
        assert result.get("reason") != "dedup"

    @patch("app.services.notification.push_service.get_china_now")
    def test_dedup_different_title_passes(self, mock_now, db):
        """不同 title 不触发 dedup（规则不同 → 允许推送）."""
        mock_now.return_value = datetime(2026, 5, 1, 14, 0)
        user_id = _make_user(db)
        _make_settings(db, user_id)

        db.add(NotificationLog(
            user_id=user_id,
            notification_type="health_alert",
            channel="ios_apns",
            title="⚠️ BP Spike",
            content="earlier",
            status=NotificationStatus.SENT.value,
            sent_at=datetime(2026, 5, 1, 13, 0),
        ))
        db.commit()

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ HRV 异常",
                content="different alert",
                severity="high",
                channels=["ios_apns"],
            ))
        assert result.get("reason") != "dedup"
