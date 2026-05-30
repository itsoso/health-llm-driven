"""test_push_quiet_hours_strict —— 静默时段策略.

2026-05-30 (反转 2026-05-11): critical 健康告警穿透静默立即推送; 其余 severity 仍延迟.

覆盖:
- High/Medium 静默时段进 delayed 队列
- Critical 静默时段穿透立即推 (不延迟)
- Info/Low 被 threshold 拦截, 不进 delayed
- Critical 非静默时段仍立刻推
- next_quiet_hours_end 计算正确
- flush_delayed_pushes 跳过未到点的, 处理已到点的
- flush 后 status 转 sent
"""

from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import pytest

from app.models.notification import (
    NotificationLog,
    NotificationStatus,
    UserNotificationSetting,
)
from app.models.user import User
from app.services.notification.push_service import PushService
from app.utils.timezone import get_china_now


def _make_user(db, username="strict_user"):
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        name=username,
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    settings = UserNotificationSetting(
        user_id=user.id,
        enabled=True,
        ios_push_enabled=True,
        ios_device_token="dummy_token",
        quiet_hours_start="22:00",
        quiet_hours_end="08:30",
    )
    db.add(settings)
    db.commit()
    return user


@pytest.mark.parametrize("severity", ["medium", "high"])
@pytest.mark.asyncio
async def test_quiet_hours_delays_non_critical_severities(db, severity):
    """非 critical 的够级别告警在静默时段延迟到 08:30.

    注: info/low 在 alert_severity_threshold='warning' (默认) 下会被更早的
    threshold 检查拦截, 不会走到 quiet_hours 路径. critical 单独测 (穿透).
    """
    user = _make_user(db, username=f"strict_{severity}")
    svc = PushService(db)

    # mock 当前时间为凌晨 03:00
    fake_now = datetime(2026, 5, 12, 3, 0, 0)
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now):
        result = await svc.send_notification(
            user_id=user.id,
            notification_type="health_alert",
            title="测试告警",
            content="content",
            severity=severity,
            data={"rule_id": f"test.rule.{severity}"},
        )

    assert result["success"] is False
    assert result["reason"] == "delayed_for_quiet_hours"
    assert "scheduled_at" in result

    delayed = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.status == NotificationStatus.DELAYED.value,
        )
        .all()
    )
    assert len(delayed) == 1
    log = delayed[0]
    assert log.scheduled_at is not None
    # scheduled_at 应在 fake_now 之后, 且对应 08:30
    assert log.scheduled_at.hour == 8
    assert log.scheduled_at.minute == 30
    # 还是同一天的 08:30 (因为 fake_now 是 03:00 之前)
    assert log.scheduled_at.day == fake_now.day


@pytest.mark.asyncio
async def test_quiet_hours_critical_bypasses_immediately(db):
    """critical 健康告警穿透静默时段立即推送 (2026-05-30 反转"严格不打扰").

    致命药物交互 / 急性阈值不应压到早上 08:30 —— 原计划的"紧急联系人穿透"从未落地.
    """
    user = _make_user(db, username="strict_critical_bypass")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 3, 0, 0)  # 凌晨静默时段
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now), \
         patch.object(PushService, "_send_ios", new=AsyncMock(return_value={"success": True})):
        result = await svc.send_notification(
            user_id=user.id,
            notification_type="health_alert",
            title="紧急: 致命药物交互",
            content="content",
            severity="critical",
            data={"rule_id": "ddi.fatal"},
        )

    # 立即发送, 不进延迟队列
    assert result.get("success") is True
    assert result.get("reason") != "delayed_for_quiet_hours"
    delayed = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.status == NotificationStatus.DELAYED.value,
        )
        .count()
    )
    assert delayed == 0


@pytest.mark.asyncio
async def test_quiet_hours_dedups_existing_delayed_reminder(db):
    """同一睡眠提醒在静默时段重复触发时, 只能排队 1 条 08:30 delayed。"""
    user = _make_user(db, username="quiet_dedup_sleep")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 3, 0, 0)
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now):
        first = await svc.send_notification(
            user_id=user.id,
            notification_type="reminder",
            title="💤 睡眠提醒",
            content="该准备睡觉了，保证充足睡眠，明天精神饱满！",
        )
        second = await svc.send_notification(
            user_id=user.id,
            notification_type="reminder",
            title="💤 睡眠提醒",
            content="该准备睡觉了，保证充足睡眠，明天精神饱满！",
        )

    assert first["reason"] == "delayed_for_quiet_hours"
    assert second["reason"] == "dedup"
    delayed = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.notification_type == "reminder",
            NotificationLog.title == "💤 睡眠提醒",
            NotificationLog.status == NotificationStatus.DELAYED.value,
        )
        .all()
    )
    assert len(delayed) == 1


@pytest.mark.parametrize("severity", ["info", "low"])
@pytest.mark.asyncio
async def test_low_severity_blocked_by_threshold_not_delayed(db, severity):
    """info/low 在 default threshold='warning' 下被 can_send 拦截, 不进 delayed."""
    user = _make_user(db, username=f"thresh_{severity}")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 3, 0, 0)
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now):
        result = await svc.send_notification(
            user_id=user.id,
            notification_type="health_alert",
            title="低级别告警",
            content="content",
            severity=severity,
            data={"rule_id": f"test.low.{severity}"},
        )

    assert result["success"] is False
    # 不是 delayed, 是被门槛拦截
    assert result["reason"] != "delayed_for_quiet_hours"

    delayed_count = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.status == NotificationStatus.DELAYED.value,
        )
        .count()
    )
    assert delayed_count == 0


@pytest.mark.asyncio
async def test_critical_still_immediate_outside_quiet_hours(db):
    """白天非静默时段, critical 仍立刻推, 不进 delayed."""
    user = _make_user(db, username="day_critical")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 14, 0, 0)
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now), \
         patch.object(PushService, "_send_ios", new=AsyncMock(return_value={"success": True})):
        result = await svc.send_notification(
            user_id=user.id,
            notification_type="health_alert",
            title="紧急: BP 180/120",
            content="critical",
            severity="critical",
            data={"rule_id": "vitals.bp_critical"},
        )

    assert result.get("success") is True

    delayed = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.status == NotificationStatus.DELAYED.value,
        )
        .count()
    )
    assert delayed == 0


@pytest.mark.asyncio
async def test_quiet_hours_policy_bypass_sends_immediately(db):
    """明确 bypass 的 bedtime/用户主动提醒不进入 delayed 队列."""
    user = _make_user(db, username="qh_bypass")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 3, 0, 0)
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now), \
         patch.object(PushService, "_send_ios", new=AsyncMock(return_value={"success": True})):
        result = await svc.send_notification(
            user_id=user.id,
            notification_type="reminder",
            title="睡前提醒",
            content="该睡了",
            quiet_hours_policy="bypass",
        )

    assert result.get("success") is True
    delayed = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.status == NotificationStatus.DELAYED.value,
        )
        .count()
    )
    assert delayed == 0


@pytest.mark.asyncio
async def test_quiet_hours_policy_drop_skips_without_queueing(db):
    """明确 drop 的低价值提醒在静默时段直接跳过, 不堆到早上."""
    user = _make_user(db, username="qh_drop")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 3, 0, 0)
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now):
        result = await svc.send_notification(
            user_id=user.id,
            notification_type="reminder",
            title="低价值提醒",
            content="稍后再说也可以",
            quiet_hours_policy="drop",
        )

    assert result["success"] is False
    assert result["reason"] == "dropped_for_quiet_hours"
    delayed = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.status == NotificationStatus.DELAYED.value,
        )
        .count()
    )
    assert delayed == 0


def test_next_quiet_hours_end_during_quiet(db):
    """凌晨 03:00, end=08:30 → 今天 08:30."""
    user = _make_user(db, username="qh_calc1")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 3, 0, 0)
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now):
        result = svc.next_quiet_hours_end(user.id)

    assert result.year == 2026 and result.month == 5 and result.day == 12
    assert result.hour == 8 and result.minute == 30


def test_next_quiet_hours_end_after_morning(db):
    """白天 14:00, end=08:30 → 明天 08:30."""
    user = _make_user(db, username="qh_calc2")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 14, 0, 0)
    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now):
        result = svc.next_quiet_hours_end(user.id)

    assert result.day == 13
    assert result.hour == 8 and result.minute == 30


@pytest.mark.asyncio
async def test_flush_delayed_pushes_processes_due(db):
    """flush 处理 scheduled_at <= now 的, 跳过未到点的."""
    user = _make_user(db, username="flush_user")
    svc = PushService(db)

    now = get_china_now()

    # 已到点的 delayed log
    log_due = NotificationLog(
        user_id=user.id,
        notification_type="health_alert",
        channel="multi",
        title="到点",
        content="should fire",
        data={"rule_id": "x.due", "severity": "high"},
        status=NotificationStatus.DELAYED.value,
        scheduled_at=now - timedelta(minutes=10),
    )
    # 未到点的 delayed log
    log_future = NotificationLog(
        user_id=user.id,
        notification_type="health_alert",
        channel="multi",
        title="未到点",
        content="not yet",
        data={"rule_id": "x.future", "severity": "high"},
        status=NotificationStatus.DELAYED.value,
        scheduled_at=now + timedelta(hours=2),
    )
    db.add_all([log_due, log_future])
    db.commit()

    with patch.object(PushService, "_send_ios", new=AsyncMock(return_value={"success": True})):
        result = await svc.flush_delayed_pushes()

    assert result["flushed"] == 1
    assert result["succeeded"] == 1

    db.refresh(log_due)
    db.refresh(log_future)
    assert log_due.status == NotificationStatus.SENT.value
    assert log_future.status == NotificationStatus.DELAYED.value


@pytest.mark.asyncio
async def test_flush_delayed_pushes_dedups_same_title(db):
    """历史上已经排队的重复 delayed, flush 时也只真正发第一条。"""
    user = _make_user(db, username="flush_dedup_sleep")
    svc = PushService(db)
    now = get_china_now()

    logs = [
        NotificationLog(
            user_id=user.id,
            notification_type="reminder",
            channel="multi",
            title="💤 睡眠提醒",
            content="该准备睡觉了，保证充足睡眠，明天精神饱满！",
            data={},
            status=NotificationStatus.DELAYED.value,
            scheduled_at=now - timedelta(minutes=10),
        ),
        NotificationLog(
            user_id=user.id,
            notification_type="reminder",
            channel="multi",
            title="💤 睡眠提醒",
            content="该准备睡觉了，保证充足睡眠，明天精神饱满！",
            data={},
            status=NotificationStatus.DELAYED.value,
            scheduled_at=now - timedelta(minutes=9),
        ),
    ]
    db.add_all(logs)
    db.commit()

    send_mock = AsyncMock(return_value={"success": True})
    with patch.object(PushService, "_send_ios", new=send_mock):
        result = await svc.flush_delayed_pushes()

    assert result["flushed"] == 2
    assert result["succeeded"] == 1
    assert result["deduped"] == 1
    assert send_mock.await_count == 1
    for log in logs:
        db.refresh(log)
    assert [log.status for log in logs].count(NotificationStatus.SENT.value) == 1
    assert [log.error_message for log in logs].count("dedup") == 1


@pytest.mark.asyncio
async def test_flush_does_not_re_delay(db):
    """flush 时已经过了静默时段, 但若被 mock 到静默时段, respect_quiet_hours=False 应不再延迟."""
    user = _make_user(db, username="flush_no_redelay")
    svc = PushService(db)

    fake_now = datetime(2026, 5, 12, 3, 0, 0)  # 静默时段

    log = NotificationLog(
        user_id=user.id,
        notification_type="health_alert",
        channel="multi",
        title="t",
        content="c",
        data={"rule_id": "x.r", "severity": "critical"},
        status=NotificationStatus.DELAYED.value,
        scheduled_at=fake_now - timedelta(minutes=5),
    )
    db.add(log)
    db.commit()

    with patch("app.services.notification.push_service.get_china_now", return_value=fake_now), \
         patch.object(PushService, "_send_ios", new=AsyncMock(return_value={"success": True})):
        # 这里 get_china_now 返回静默, 但 flush 内部传 respect_quiet_hours=False, 应该 sent
        result = await svc.flush_delayed_pushes()

    assert result["succeeded"] >= 1
    db.refresh(log)
    assert log.status == NotificationStatus.SENT.value
