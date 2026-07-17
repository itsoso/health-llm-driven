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


class TestCriticalDedupNarrowedWindow:
    """#4 under-alarm 修复 (2026-07-17): 持续危急值不能被 24h 去重静默丢弃.

    真实场景: Garmin 每 2h 同步 (09/11/13/.../23 点) → regenerate_briefing_for_user
    → evaluate_and_push_safety 重新检出 BP 220/130 → send_notification(severity="critical",
    rule_id="vitals.bp_crisis", 默认 dedup_window_hours=24).

    修复前: 09:01 推一条, 11:01~次日 09:00 的每次重新检出全部命中 24h 去重被静默跳过
    —— 持续的危及生命状态一天只提醒一次。
    修复后: critical 窗口收窄到 CRITICAL_DEDUP_WINDOW_HOURS(3h), 稳定"隔一次同步重推"。
    """

    def _seed_prior_critical(self, db, user_id, sent_at):
        db.add(NotificationLog(
            user_id=user_id,
            notification_type="health_alert",
            channel="ios_apns",
            title="⚠️ 血压危急",
            content="220/130",
            status=NotificationStatus.SENT.value,
            sent_at=sent_at,
            data={"rule_id": "vitals.bp_crisis"},
        ))
        db.commit()

    @patch("app.services.notification.push_service.get_china_now")
    def test_persistent_critical_realerts_after_narrowed_window(self, mock_now, db):
        """09:01 已推 → 13:01 BP 仍 220/130 → 必须重新提醒 (修复前被 24h 去重丢弃)."""
        mock_now.return_value = datetime(2026, 5, 1, 13, 1)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        self._seed_prior_critical(db, user_id, datetime(2026, 5, 1, 9, 1))

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ 血压危急",
                content="220/130 仍未缓解",
                severity="critical",
                data={"rule_id": "vitals.bp_crisis"},
                channels=["ios_apns"],
            ))
        assert result.get("reason") != "dedup"
        assert result.get("success") is True

    @patch("app.services.notification.push_service.get_china_now")
    def test_critical_still_deduped_inside_narrowed_window(self, mock_now, db):
        """收窄 ≠ 取消: 09:01 已推 → 11:01 同一 rule 仍在 3h 窗口内 → 跳过, 不刷屏."""
        mock_now.return_value = datetime(2026, 5, 1, 11, 1)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        self._seed_prior_critical(db, user_id, datetime(2026, 5, 1, 9, 1))

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ 血压危急",
                content="220/130 仍未缓解",
                severity="critical",
                data={"rule_id": "vitals.bp_crisis"},
                channels=["ios_apns"],
            ))
        assert result["success"] is False
        assert result["reason"] == "dedup"

    @patch("app.services.notification.push_service.get_china_now")
    def test_non_critical_keeps_24h_dedup(self, mock_now, db):
        """加层不减层: 只对 critical 放宽。high 在 4h 后仍走原 24h 去重, 行为零变化."""
        mock_now.return_value = datetime(2026, 5, 1, 13, 1)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        db.add(NotificationLog(
            user_id=user_id,
            notification_type="health_alert",
            channel="ios_apns",
            title="⚠️ 训练负荷偏高",
            content="ACWR 1.6",
            status=NotificationStatus.SENT.value,
            sent_at=datetime(2026, 5, 1, 9, 1),
            data={"rule_id": "training_load.acwr_high"},
        ))
        db.commit()

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ 训练负荷偏高",
                content="ACWR 1.6",
                severity="high",
                data={"rule_id": "training_load.acwr_high"},
                channels=["ios_apns"],
            ))
        assert result["success"] is False
        assert result["reason"] == "dedup"

    @patch("app.services.notification.push_service.get_china_now")
    def test_critical_does_not_add_dedup_when_caller_disabled_it(self, mock_now, db):
        """dedup_window_hours=0 (调用方显式关去重) 不能因为 critical 被"补"上 3h 抑制."""
        mock_now.return_value = datetime(2026, 5, 1, 9, 31)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        self._seed_prior_critical(db, user_id, datetime(2026, 5, 1, 9, 1))

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ 血压危急",
                content="220/130 仍未缓解",
                severity="critical",
                data={"rule_id": "vitals.bp_crisis"},
                dedup_window_hours=0,
                channels=["ios_apns"],
            ))
        assert result.get("reason") != "dedup"

    @patch("app.services.notification.push_service.get_china_now")
    def test_critical_narrower_caller_window_not_widened(self, mock_now, db):
        """min() 语义: 调用方给的 1h 比 3h 更窄 → 保持 1h, 绝不被放大成 3h 抑制."""
        mock_now.return_value = datetime(2026, 5, 1, 11, 1)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        self._seed_prior_critical(db, user_id, datetime(2026, 5, 1, 9, 1))

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ 血压危急",
                content="220/130 仍未缓解",
                severity="critical",
                data={"rule_id": "vitals.bp_crisis"},
                dedup_window_hours=1,
                channels=["ios_apns"],
            ))
        assert result.get("reason") != "dedup"

    @patch("app.services.notification.push_service.get_china_now")
    def test_night_critical_does_not_pile_up_delayed_rows(self, mock_now, db):
        """收窄窗口不能让夜间 critical 堆成多条 delayed → 09:00 一起 flush 刷屏.

        这是 send_notification "去重检查必须先于 quiet-hours 延迟队列" 那段注释要防的
        不变量。正确性依赖 _find_dedup_log 的过滤**只有下界**: delayed row 的
        dedup_time = coalesce(sent_at=NULL, scheduled_at=09:00) 是未来时刻, 恒 >=
        任何过去的 window_start, 所以窗口再窄也命中。若有人给 _find_dedup_log 加
        `dedup_time <= now` 上界, 这个测试会红。
        """
        user_id = _make_user(db)
        _make_settings(db, user_id)  # quiet 22:00–09:00
        svc = PushService(db)

        # 夜间同一 rule 反复触发 (真实来源: wscla escalate, crontab(minute=15) 每小时)
        for hh, mm in [(0, 15), (2, 15), (5, 15), (7, 15)]:
            mock_now.return_value = datetime(2026, 5, 1, hh, mm)
            with patch.object(PushService, "_send_ios", return_value={"success": True}):
                asyncio.run(svc.send_notification(
                    user_id=user_id,
                    notification_type="health_alert",
                    title="⚠️ 血压危急",
                    content="220/130 仍未缓解",
                    severity="critical",
                    data={"rule_id": "vitals.bp_crisis"},
                    channels=["ios_apns"],
                ))

        delayed = db.query(NotificationLog).filter(
            NotificationLog.user_id == user_id,
            NotificationLog.status == NotificationStatus.DELAYED.value,
        ).count()
        assert delayed == 1, f"夜间 delayed 堆积成 {delayed} 条 → 09:00 会刷屏"

    @patch("app.services.notification.push_service.get_china_now")
    def test_persistent_critical_realert_ladder_over_real_sync_cadence(self, mock_now, db):
        """CRITICAL_DEDUP_WINDOW_HOURS=3 这个魔数的可执行论证.

        按真实 Garmin crontab (北京 09/11/13/15/17/19/21/23 点 :01) 跑一整天持续
        BP 220/130 → 必须稳定"隔一次同步重推" = 09/13/17/21, 共 4 条/天,
        与产品 owner 选的"每 4 小时重新提醒一次"一致。
        窗口若取 2h 整数倍(如 4h)会正好落在同步刻度上 → 秒级抖动决定命中与否。
        """
        user_id = _make_user(db)
        _make_settings(db, user_id)
        svc = PushService(db)

        sent_hours = []
        for hh in [9, 11, 13, 15, 17, 19, 21, 23]:
            mock_now.return_value = datetime(2026, 5, 1, hh, 1)
            with patch.object(PushService, "_send_ios", return_value={"success": True}):
                result = asyncio.run(svc.send_notification(
                    user_id=user_id,
                    notification_type="health_alert",
                    title="⚠️ 血压危急",
                    content="220/130 仍未缓解",
                    severity="critical",
                    data={"rule_id": "vitals.bp_crisis"},
                    channels=["ios_apns"],
                ))
            if result.get("reason") != "dedup":
                sent_hours.append(hh)

        assert sent_hours == [9, 13, 17, 21], f"重提醒阶梯漂移: {sent_hours}"

    @patch("app.services.notification.push_service.get_china_now")
    def test_critical_min_overrides_caller_long_window(self, mock_now, db):
        """契约: min() 会无差别压掉调用方显式设的长窗口 (garmin_sync 的 168h → 3h).

        钉成"已知且有意"。今天 _push_episode_created 有 Episode 幂等闸 +
        每 episode 唯一 rule_id, 那 168h 从未被行使 → 行为零变化。
        若将来真需要长抑制的 critical, 必须显式豁免, 不能默默依赖 min()。
        """
        mock_now.return_value = datetime(2026, 5, 1, 13, 1)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        self._seed_prior_critical(db, user_id, datetime(2026, 5, 1, 9, 1))

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ 血压危急",
                content="220/130 仍未缓解",
                severity="critical",
                data={"rule_id": "vitals.bp_crisis"},
                dedup_window_hours=168,  # 调用方要 7 天; critical 下实际生效 3h
                channels=["ios_apns"],
            ))
        assert result.get("reason") != "dedup"

    @patch("app.services.notification.push_service.get_china_now")
    def test_uppercase_critical_still_narrowed(self, mock_now, db):
        """_severity_rank 走 .lower(): "CRITICAL" 也必须收窄, 不能漏成 24h."""
        mock_now.return_value = datetime(2026, 5, 1, 13, 1)
        user_id = _make_user(db)
        _make_settings(db, user_id)
        self._seed_prior_critical(db, user_id, datetime(2026, 5, 1, 9, 1))

        svc = PushService(db)
        with patch.object(PushService, "_send_ios", return_value={"success": True}):
            result = asyncio.run(svc.send_notification(
                user_id=user_id,
                notification_type="health_alert",
                title="⚠️ 血压危急",
                content="220/130 仍未缓解",
                severity="CRITICAL",
                data={"rule_id": "vitals.bp_crisis"},
                channels=["ios_apns"],
            ))
        assert result.get("reason") != "dedup"
