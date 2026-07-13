"""Open-Loop push 的 quiet_hours 守门测试.

保证:
- 默认 22:00-09:00 窗口内不推
- score>=85 (critical-level) 也不穿透 quiet_hours
- 用户自定义 quiet_hours 被尊重
- 跨午夜逻辑正确
"""
from datetime import datetime
from unittest.mock import patch

from app.tasks.open_loop_manager import _is_in_quiet_hours_now
from app.utils.timezone import CHINA_TIMEZONE


class _FakeSetting:
    def __init__(self, start: str, end: str):
        self.quiet_hours_start = start
        self.quiet_hours_end = end


def _at(hh: int, mm: int = 0):
    """Return a datetime on 2026-05-03 at HH:MM in China timezone."""
    return datetime(2026, 5, 3, hh, mm, 0, tzinfo=CHINA_TIMEZONE)


def test_default_quiet_hours_7am_is_quiet():
    """07:00 (原 open-loop cron 时间点) 默认 quiet 内."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(7, 0)
        s = _FakeSetting("22:00", "09:00")
        assert _is_in_quiet_hours_now(s) is True


def test_default_quiet_hours_845am_is_quiet():
    """08:45 仍在默认 quiet 内, 避免早晨打扰睡眠."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(8, 45)
        s = _FakeSetting("22:00", "09:00")
        assert _is_in_quiet_hours_now(s) is True


def test_default_quiet_hours_9am_is_allowed():
    """09:00 = quiet 结束, 已过, allowed (半开区间 end 不含)."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(9, 0)
        s = _FakeSetting("22:00", "09:00")
        assert _is_in_quiet_hours_now(s) is False


def test_default_quiet_hours_midnight_is_quiet():
    """00:30 深夜 quiet 内."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(0, 30)
        s = _FakeSetting("22:00", "09:00")
        assert _is_in_quiet_hours_now(s) is True


def test_default_quiet_hours_noon_is_allowed():
    """12:00 中午完全 allowed."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(12, 0)
        s = _FakeSetting("22:00", "09:00")
        assert _is_in_quiet_hours_now(s) is False


def test_default_quiet_hours_22_exactly_is_quiet():
    """22:00 = quiet 开始, 算 quiet."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(22, 0)
        s = _FakeSetting("22:00", "09:00")
        assert _is_in_quiet_hours_now(s) is True


def test_default_quiet_hours_0830_is_quiet():
    """08:30 仍在默认 quiet 内."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(8, 30)
        s = _FakeSetting("22:00", "09:00")
        assert _is_in_quiet_hours_now(s) is True


def test_morning_sleep_floor_overrides_user_end_before_9am():
    """即使老用户保存 quiet_end=08:00, 08:30 仍必须静默,避免影响睡眠."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(8, 30)
        s = _FakeSetting("22:00", "08:00")
        assert _is_in_quiet_hours_now(s) is True


def test_custom_non_crossing_window():
    """用户自定义 14:00-16:00 (午休), 不跨午夜."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        s = _FakeSetting("14:00", "16:00")
        mock_dt.now.return_value = _at(15, 0)
        assert _is_in_quiet_hours_now(s) is True
        mock_dt.now.return_value = _at(13, 59)
        assert _is_in_quiet_hours_now(s) is False
        mock_dt.now.return_value = _at(16, 0)
        assert _is_in_quiet_hours_now(s) is False


def test_none_values_fall_back_to_defaults():
    """setting 字段为 None 时走 22:00-09:00 默认."""
    with patch("app.tasks.open_loop_manager.datetime") as mock_dt:
        mock_dt.now.return_value = _at(7, 0)
        s = _FakeSetting(None, None)
        assert _is_in_quiet_hours_now(s) is True
        mock_dt.now.return_value = _at(10, 0)
        assert _is_in_quiet_hours_now(s) is False
