"""
P8 (2026-05-04): snooze 到期续约 — 推送 body 前加"上次你说先暂停, 现在到期了 — "
让用户感受续约而非重复打扰.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.tasks.open_loop_manager import OpenLoop, _push_loop


def _make_setting(user_id: int = 1, token: str = "a" * 64):
    from app.models.notification import UserNotificationSetting
    return UserNotificationSetting(
        user_id=user_id, enabled=True, ios_push_enabled=True,
        ios_device_token=token, health_alert_enabled=True,
        quiet_hours_start="22:00", quiet_hours_end="08:30",
        alert_severity_threshold="warning",
    )


def test_recently_expired_snooze_adds_renewal_prefix(db):
    """24h 内刚过期的 snooze 记录 → body 前加续约前缀."""
    from app.models.open_loop_history import OpenLoopHistory

    db.add(_make_setting(user_id=1))
    # 一条 6 小时前刚 snooze 到期的记录
    db.add(OpenLoopHistory(
        user_id=1, kind="lab_overdue", signal_key="LDL",
        score=80, title="X", body="Y",
        delivery_ok=1,
        snoozed_until=datetime.now(timezone.utc) - timedelta(hours=6),
        sent_at=datetime.now(timezone.utc) - timedelta(days=10),
    ))
    db.commit()

    loop = OpenLoop(
        user_id=1, kind="lab_overdue", signal_key="LDL",
        score=160, title="LDL 是时候复查了",
        body="200 天前是 4.1, 这周抽时间去测一下",
        deeplink="health://medical-exams/upload",
    )

    captured = {}
    async def fake_send(**kw):
        captured.update(kw)
        return {"success": True}
    mock_service = MagicMock()
    mock_service.is_configured = True
    mock_service.send_push = fake_send

    with patch("app.services.notification.ios_push.IOSPushService", return_value=mock_service), \
         patch("app.tasks.open_loop_manager._is_in_quiet_hours_now", return_value=False), \
         patch("app.services.notification.push_service.PushService.is_quiet_hours", return_value=False):
        ok = _push_loop(db, user_id=1, loop=loop)

    assert ok is True
    # body 必须以续约前缀开头
    assert "上次你说先暂停" in loop.body
    assert "现在到期了" in loop.body
    # 原始 body 内容仍保留
    assert "200 天前是 4.1" in loop.body


def test_no_snooze_history_no_prefix(db):
    """没有 snooze 历史的首次推送 → body 不加续约前缀."""
    db.add(_make_setting(user_id=1))
    db.commit()

    loop = OpenLoop(
        user_id=1, kind="lab_overdue", signal_key="HbA1c",
        score=160, title="X", body="原始 body",
    )

    captured = {}
    async def fake_send(**kw):
        captured.update(kw)
        return {"success": True}
    mock_service = MagicMock()
    mock_service.is_configured = True
    mock_service.send_push = fake_send

    with patch("app.services.notification.ios_push.IOSPushService", return_value=mock_service), \
         patch("app.tasks.open_loop_manager._is_recently_pushed_or_snoozed", return_value=False), \
         patch("app.tasks.open_loop_manager._is_in_quiet_hours_now", return_value=False), \
         patch("app.services.notification.push_service.PushService.is_quiet_hours", return_value=False):
        ok = _push_loop(db, user_id=1, loop=loop)

    assert ok is True
    assert loop.body == "原始 body"
    assert "上次你说先暂停" not in loop.body


def test_old_expired_snooze_beyond_24h_no_prefix(db):
    """snooze 在 25 小时前过期 — 太久, 不再续约 (避免无限催)."""
    from app.models.open_loop_history import OpenLoopHistory

    db.add(_make_setting(user_id=1))
    # 25 小时前过期 — 超过 24h 续约窗口
    db.add(OpenLoopHistory(
        user_id=1, kind="plan_drift", signal_key="template_id=1",
        score=80, title="X", body="Y",
        delivery_ok=1,
        snoozed_until=datetime.now(timezone.utc) - timedelta(hours=25),
        sent_at=datetime.now(timezone.utc) - timedelta(days=14),
    ))
    db.commit()

    loop = OpenLoop(
        user_id=1, kind="plan_drift", signal_key="template_id=1",
        score=80, title="X", body="原始 body",
    )

    mock_service = MagicMock()
    mock_service.is_configured = True
    async def fake_send(**kw):
        return {"success": True}
    mock_service.send_push = fake_send

    with patch("app.services.notification.ios_push.IOSPushService", return_value=mock_service), \
         patch("app.tasks.open_loop_manager._is_recently_pushed_or_snoozed", return_value=False), \
         patch("app.tasks.open_loop_manager._is_in_quiet_hours_now", return_value=False):
        _push_loop(db, user_id=1, loop=loop)

    assert "上次你说先暂停" not in loop.body


def test_future_snooze_still_active_no_prefix(db):
    """snoozed_until 在未来 (snooze 仍生效) — 这种情况 dedup 已拦截, 走不到续约逻辑.
    但作为 sanity 测试: 即便走到续约函数也不该加前缀 (因为还没过期).
    """
    from app.models.open_loop_history import OpenLoopHistory
    from app.tasks.open_loop_manager import _maybe_apply_snooze_renewal_prefix

    db.add(_make_setting(user_id=1))
    db.add(OpenLoopHistory(
        user_id=1, kind="lab_overdue", signal_key="ALT",
        score=80, title="X", body="Y",
        delivery_ok=1,
        snoozed_until=datetime.now(timezone.utc) + timedelta(days=2),
        sent_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db.commit()

    loop = OpenLoop(
        user_id=1, kind="lab_overdue", signal_key="ALT",
        score=80, title="X", body="原始",
    )
    _maybe_apply_snooze_renewal_prefix(db, user_id=1, loop=loop)
    assert loop.body == "原始"


def test_other_user_snooze_no_cross_contamination(db):
    """user_id=2 的 snooze 不能影响 user_id=1 的 loop."""
    from app.models.open_loop_history import OpenLoopHistory
    from app.tasks.open_loop_manager import _maybe_apply_snooze_renewal_prefix

    db.add(OpenLoopHistory(
        user_id=2, kind="lab_overdue", signal_key="LDL",
        score=80, title="X", body="Y",
        delivery_ok=1,
        snoozed_until=datetime.now(timezone.utc) - timedelta(hours=3),
        sent_at=datetime.now(timezone.utc) - timedelta(days=10),
    ))
    db.commit()

    loop = OpenLoop(
        user_id=1, kind="lab_overdue", signal_key="LDL",
        score=80, title="X", body="原始",
    )
    _maybe_apply_snooze_renewal_prefix(db, user_id=1, loop=loop)
    assert loop.body == "原始"
