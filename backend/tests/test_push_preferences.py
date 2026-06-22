"""H1-B 推送规则分级 + 用户偏好测试.

覆盖:
- alert_severity_threshold: info/warning/critical 过滤
- alert_rule_opt_outs: rule_id mute 列表
- rule-aware dedup: 同 rule_id 窗口内只推一次 (与 title 无关)
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.models.notification import (
    UserNotificationSetting, NotificationLog, NotificationType, NotificationStatus,
)
from app.services.notification.push_service import PushService, _severity_rank


# ─────────── severity 排序 ───────────


class TestSeverityRank:
    def test_order(self):
        assert _severity_rank("info") < _severity_rank("warning")
        assert _severity_rank("warning") < _severity_rank("high")
        assert _severity_rank("high") < _severity_rank("critical")
        # medium 与 warning 同级 (legacy 对齐)
        assert _severity_rank("medium") == _severity_rank("warning")

    def test_unknown_defaults_zero(self):
        assert _severity_rank("nonsense") == 0
        assert _severity_rank(None) == 0


# ─────────── can_send_notification ───────────


def _mk_settings(db, user_id=1, **overrides):
    s = UserNotificationSetting(user_id=user_id, enabled=True, **overrides)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class TestSeverityThreshold:
    def test_below_threshold_rejected(self, db):
        _mk_settings(db, alert_severity_threshold="warning")
        ps = PushService(db)
        assert not ps.can_send_notification(
            1, "health_alert", severity="info",
        )

    def test_at_threshold_allowed(self, db):
        _mk_settings(db, alert_severity_threshold="warning")
        ps = PushService(db)
        assert ps.can_send_notification(
            1, "health_alert", respect_quiet_hours=False, severity="warning",
        )

    def test_above_threshold_allowed(self, db):
        _mk_settings(db, alert_severity_threshold="warning")
        ps = PushService(db)
        assert ps.can_send_notification(
            1, "health_alert", respect_quiet_hours=False, severity="critical",
        )

    def test_threshold_only_applies_to_health_alert(self, db):
        _mk_settings(db, alert_severity_threshold="critical")
        ps = PushService(db)
        # morning_briefing 不受 alert threshold 影响
        assert ps.can_send_notification(
            1, "morning_briefing", respect_quiet_hours=False, severity="info",
        )


class TestRuleOptOut:
    def test_muted_rule_rejected(self, db):
        _mk_settings(
            db,
            alert_severity_threshold="info",
            alert_rule_opt_outs=["vitals.sleep_short"],
        )
        ps = PushService(db)
        assert not ps.can_send_notification(
            1, "health_alert", respect_quiet_hours=False,
            severity="high", rule_id="vitals.sleep_short",
        )

    def test_non_muted_rule_allowed(self, db):
        _mk_settings(
            db,
            alert_severity_threshold="info",
            alert_rule_opt_outs=["vitals.sleep_short"],
        )
        ps = PushService(db)
        assert ps.can_send_notification(
            1, "health_alert", respect_quiet_hours=False,
            severity="high", rule_id="ddi.warfarin_nsaid",
        )

    def test_opt_out_only_applies_to_health_alert(self, db):
        _mk_settings(db, alert_rule_opt_outs=["vitals.sleep_short"])
        ps = PushService(db)
        # 其他类型不看 rule_id
        assert ps.can_send_notification(
            1, "reminder", respect_quiet_hours=False,
            severity="info", rule_id="vitals.sleep_short",
        )

    def test_no_rule_id_bypasses_opt_out(self, db):
        _mk_settings(
            db,
            alert_severity_threshold="info",
            alert_rule_opt_outs=["vitals.sleep_short"],
        )
        ps = PushService(db)
        # 没 rule_id 就不参与 opt-out 逻辑, 仍放行
        assert ps.can_send_notification(
            1, "health_alert", respect_quiet_hours=False,
            severity="high", rule_id=None,
        )


# ─────────── rule-aware dedup (query-level 测试) ───────────


class TestRuleAwareDedup:
    """只测 SQLite fallback 路径 (conftest 用的就是 SQLite)."""

    def _insert_sent_log(self, db, user_id=1, rule_id="vitals.sleep_short",
                        sent_minutes_ago=10):
        sent_at = datetime.now(timezone.utc) - timedelta(minutes=sent_minutes_ago)
        log = NotificationLog(
            user_id=user_id,
            notification_type="health_alert",
            channel="ios_apns",
            title="⚠️ 睡眠过短",
            content="昨晚睡眠 4.5h",
            data={"rule_id": rule_id},
            status=NotificationStatus.SENT.value,
            sent_at=sent_at,
        )
        db.add(log)
        db.commit()
        return log

    def test_same_rule_id_detected_as_dup(self, db):
        _mk_settings(db, alert_severity_threshold="info")
        self._insert_sent_log(db, rule_id="vitals.sleep_short")

        # SQLite fallback: LIKE '%"rule_id": "..."%'  必须能匹配
        q = db.query(NotificationLog).filter(
            NotificationLog.user_id == 1,
            NotificationLog.data.like('%"rule_id": "vitals.sleep_short"%'),
        )
        assert q.count() == 1

    def test_different_rule_id_not_dup(self, db):
        self._insert_sent_log(db, rule_id="vitals.sleep_short")
        q = db.query(NotificationLog).filter(
            NotificationLog.user_id == 1,
            NotificationLog.data.like('%"rule_id": "ddi.warfarin_nsaid"%'),
        )
        assert q.count() == 0


class TestTelegramFallback:
    class _ConfiguredTelegram:
        configured = True

        async def send_health_alert(self, **kwargs):
            return {"success": True}

    def test_reminders_do_not_fall_back_to_global_telegram_chat(self, db, monkeypatch):
        _mk_settings(db, user_id=3, reminder_enabled=True, ios_push_enabled=False, wechat_enabled=False)
        monkeypatch.setattr(PushService, "telegram", property(lambda self: TestTelegramFallback._ConfiguredTelegram()))
        # 钉死墙钟到白天:即便 quiet_hours_policy=bypass,reminder 仍受 08:00 morning-floor 约束
        # (f7793136),北京 00:00–08:00 跑会被延迟 → reason 变 'delayed_for_quiet_hours' 而非
        # '没有可用的推送渠道',随墙钟夜间确定性失败。本测试只验 telegram fallback 路由,与时段无关。
        import app.services.notification.push_service as _push_mod
        monkeypatch.setattr(_push_mod, "get_china_now", lambda: datetime(2026, 5, 12, 14, 0, 0))

        result = asyncio.run(PushService(db).send_notification(
            user_id=3,
            notification_type=NotificationType.REMINDER.value,
            title="💤 睡眠提醒",
            content="该准备睡觉了，保证充足睡眠，明天精神饱满！",
            quiet_hours_policy="bypass",
        ))

        assert result["success"] is False
        assert result["reason"] == "没有可用的推送渠道"
        assert db.query(NotificationLog).count() == 0

    def test_health_alerts_can_still_use_global_telegram_fallback(self, db, monkeypatch):
        _mk_settings(db, user_id=3, ios_push_enabled=False, wechat_enabled=False)
        monkeypatch.setattr(PushService, "telegram", property(lambda self: TestTelegramFallback._ConfiguredTelegram()))
        # 钉死墙钟到白天(见上一测试注释):morning-floor 在北京凌晨会延迟 bypass push → success=False。
        import app.services.notification.push_service as _push_mod
        monkeypatch.setattr(_push_mod, "get_china_now", lambda: datetime(2026, 5, 12, 14, 0, 0))

        # quiet_hours_policy="bypass": 本测试只验 telegram fallback 路由, 不验静默时段。
        # 不加的话, #6 (be3b17ac) 起 warning 级 health_alert 在 22:00–08:30 会走延迟分支
        # 返回 success=False → 测试随墙钟时间在夜间确定性失败 (CI 跑在 UTC 夜 = 北京凌晨).
        result = asyncio.run(PushService(db).send_notification(
            user_id=3,
            notification_type=NotificationType.HEALTH_ALERT.value,
            title="⚠️ 健康提醒",
            content="这是需要关注的健康提醒。",
            severity="warning",
            quiet_hours_policy="bypass",
        ))

        assert result["success"] is True
        assert result["channels"]["telegram"]["success"] is True


class TestDelayedPushFlush:
    async def _ok_ios(self, *args, **kwargs):
        return {"success": True}

    def test_flush_reuses_delayed_log_instead_of_creating_duplicate_sent_log(self, db, monkeypatch):
        """flush delayed push 只能把原 delayed row 改 sent, 不能额外新增 sent row."""
        _mk_settings(
            db,
            user_id=3,
            reminder_enabled=True,
            ios_push_enabled=True,
            ios_device_token="apns-token",
            wechat_enabled=False,
        )
        # 钉死墙钟到白天非静默、且过 08:00 morning-floor 的时点:flush 重发会再过静默/晨间闸,
        # 北京 00:00–08:00 跑会被 morning-floor 再延迟 → flushed/succeeded=0(墙钟夜间失败)。
        # scheduled_at 必须相对同一 fake_now(否则 scheduled_at <= now 判定随真实墙钟漂移)。
        fake_now = datetime(2026, 5, 12, 14, 0, 0)
        delayed = NotificationLog(
            user_id=3,
            notification_type=NotificationType.REMINDER.value,
            channel="multi",
            title="💤 睡眠提醒",
            content="该准备睡觉了",
            data={"reminder_id": 99, "reminder_type": "sleep"},
            status=NotificationStatus.DELAYED.value,
            scheduled_at=fake_now - timedelta(minutes=1),
        )
        db.add(delayed)
        db.commit()
        monkeypatch.setattr(PushService, "telegram", property(lambda self: TestTelegramFallback._ConfiguredTelegram()))
        monkeypatch.setattr(PushService, "_send_ios", self._ok_ios)
        import app.services.notification.push_service as _push_mod
        monkeypatch.setattr(_push_mod, "get_china_now", lambda: fake_now)

        result = asyncio.run(PushService(db).flush_delayed_pushes())

        assert result["flushed"] == 1
        assert result["succeeded"] == 1
        logs = db.query(NotificationLog).all()
        assert len(logs) == 1
        assert logs[0].status == NotificationStatus.SENT.value
        assert logs[0].sent_at is not None
        assert logs[0].channels == [{"name": "ios_apns", "status": "sent", "error": None}]
