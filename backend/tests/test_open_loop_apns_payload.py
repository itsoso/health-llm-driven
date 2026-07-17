"""
回归测试: Open-Loop APNs payload 的 data key 必须与 mobile useNotifications.ts 对齐.

历史 bug (2026-05-04 audit 发现): backend 把 deeplink 写成 'deeplink' (无下划线),
但 mobile 读 'deep_link' (有下划线), 导致用户点 Open-Loop 推送时跳默认 tab,
看不到推送对应内容, user_action 永远 0. 修复后必须用本测试守护 key 名不漂移.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.tasks.open_loop_manager import OpenLoop, _push_loop


@pytest.fixture
def captured_send_push_kwargs():
    """构造一个能记录 IOSPushService.send_push() 实际入参的 mock service."""
    captured = {}

    async def fake_send_push(**kwargs):
        captured.update(kwargs)
        return {"success": True}

    mock_service = MagicMock()
    mock_service.is_configured = True
    mock_service.send_push = fake_send_push
    return captured, mock_service


def _make_setting(user_id: int = 1, token: str = "a" * 64):
    """返回 UserNotificationSetting mock, 满足 _push_loop 的所有 gate."""
    from app.models.notification import UserNotificationSetting
    setting = UserNotificationSetting(
        user_id=user_id,
        enabled=True,
        ios_push_enabled=True,
        ios_device_token=token,
        health_alert_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="08:30",
        alert_severity_threshold="warning",
    )
    return setting


def test_open_loop_apns_payload_uses_deep_link_key_with_underscore(db, captured_send_push_kwargs):
    """守护 bug 修复: data key 是 'deep_link' (下划线) 与 mobile 对齐, 不是 'deeplink'."""
    captured, mock_service = captured_send_push_kwargs

    db.add(_make_setting(user_id=1))
    db.commit()

    loop = OpenLoop(
        user_id=1,
        kind="lab_overdue",
        signal_key="LDL",
        score=160,
        title="该复查 LDL 了",
        body="180 天没复查",
        deeplink="health://medical-exams/upload",
    )

    # PushService 延迟加载 IOSPushService，patch class 仍能捕获统一管线的 APNs 入参。
    with patch("app.services.notification.ios_push.IOSPushService", return_value=mock_service), \
         patch("app.tasks.open_loop_manager._is_recently_pushed_or_snoozed", return_value=False), \
         patch("app.tasks.open_loop_manager._is_in_quiet_hours_now", return_value=False), \
         patch("app.services.notification.push_service.PushService.is_quiet_hours", return_value=False):
        ok = _push_loop(db, user_id=1, loop=loop)

    assert ok is True
    data = captured.get("data", {})
    # 关键断言: 必须是 deep_link (下划线), mobile useNotifications.ts:122 读这个 key
    assert "deep_link" in data, (
        f"APNs data 里必须有 'deep_link' key (mobile 读这个), "
        f"实际 keys: {list(data.keys())}"
    )
    assert data["deep_link"] == "health://medical-exams/upload"
    # 反向防御: 不能再有旧的 'deeplink' 拼写错
    assert "deeplink" not in data, (
        "不要再写 'deeplink' (无下划线) — mobile 读不到, 用户点推送跳默认 tab. "
        f"实际 data: {data}"
    )


def test_open_loop_lock_screen_copy_is_generic(db, captured_send_push_kwargs):
    """化验项目和值不得出现在锁屏可见 title/body，详细数据走 data。"""
    captured, mock_service = captured_send_push_kwargs
    db.add(_make_setting(user_id=1))
    db.commit()

    loop = OpenLoop(
        user_id=1,
        kind="lab_overdue",
        signal_key="LDL",
        score=160,
        title="LDL 是时候复查了",
        body="180 天前是 4.1",
        deeplink="health://medical-exams/upload",
        metadata={"code": "LDL", "last_value": 4.1},
    )
    with patch("app.services.notification.ios_push.IOSPushService", return_value=mock_service), \
         patch("app.tasks.open_loop_manager._is_recently_pushed_or_snoozed", return_value=False), \
         patch("app.tasks.open_loop_manager._is_in_quiet_hours_now", return_value=False), \
         patch("app.services.notification.push_service.PushService.is_quiet_hours", return_value=False):
        assert _push_loop(db, user_id=1, loop=loop) is True

    assert captured["title"] == "化验指标提醒"
    assert "LDL" not in captured["title"]
    assert "4.1" not in captured["body"]
    assert captured["data"]["metadata"]["code"] == "LDL"


def test_open_loop_apns_payload_includes_history_id(db, captured_send_push_kwargs):
    """history_id 必须随 payload 下发, mobile 才能 POST feedback."""
    captured, mock_service = captured_send_push_kwargs

    db.add(_make_setting(user_id=1))
    db.commit()

    loop = OpenLoop(
        user_id=1, kind="plan_drift", signal_key="checkin_25", score=95,
        title="拉伸断了 61 天", body="...", deeplink="health://checkin/25",
    )

    with patch("app.services.notification.ios_push.IOSPushService", return_value=mock_service), \
         patch("app.tasks.open_loop_manager._is_recently_pushed_or_snoozed", return_value=False), \
         patch("app.tasks.open_loop_manager._is_in_quiet_hours_now", return_value=False), \
         patch("app.services.notification.push_service.PushService.is_quiet_hours", return_value=False):
        _push_loop(db, user_id=1, loop=loop)

    data = captured.get("data", {})
    assert "history_id" in data
    assert data["history_id"]  # non-empty (str of int)
    assert data["history_id"].isdigit() or data["history_id"] == ""


def test_open_loop_empty_deeplink_passes_empty_string(db, captured_send_push_kwargs):
    """没有 deeplink 的循环 (如 deploy_verify) 仍能推送, deep_link='' 不应崩."""
    captured, mock_service = captured_send_push_kwargs

    db.add(_make_setting(user_id=1))
    db.commit()

    loop = OpenLoop(
        user_id=1, kind="deploy_verify", signal_key="ship_2026_05",
        score=100, title="部署验证", body="新版已上线",
    )

    with patch("app.services.notification.ios_push.IOSPushService", return_value=mock_service), \
         patch("app.tasks.open_loop_manager._is_recently_pushed_or_snoozed", return_value=False), \
         patch("app.tasks.open_loop_manager._is_in_quiet_hours_now", return_value=False), \
         patch("app.services.notification.push_service.PushService.is_quiet_hours", return_value=False):
        ok = _push_loop(db, user_id=1, loop=loop)

    assert ok is True
    assert captured.get("data", {}).get("deep_link") == ""


def test_open_loop_quiet_hours_blocks_high_score_push(db, captured_send_push_kwargs):
    """严格不打扰: 高分 Open-Loop 也不能在 quiet-hours 直连 APNs 穿透."""
    captured, mock_service = captured_send_push_kwargs

    db.add(_make_setting(user_id=1))
    db.commit()

    loop = OpenLoop(
        user_id=1,
        kind="lab_overdue",
        signal_key="LDL",
        score=160,
        title="该复查 LDL 了",
        body="180 天没复查",
        deeplink="health://medical-exams/upload",
    )

    with patch("app.services.notification.ios_push.IOSPushService", return_value=mock_service), \
         patch("app.tasks.open_loop_manager._is_recently_pushed_or_snoozed", return_value=False), \
         patch("app.tasks.open_loop_manager._is_in_quiet_hours_now", return_value=True):
        ok = _push_loop(db, user_id=1, loop=loop)

    assert ok is False
    assert captured == {}
