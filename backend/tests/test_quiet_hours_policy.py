"""resolve_quiet_hours_policy —— critical 穿透静默时段的回归测试 (Tier 0 ①).

2026-05-30 反转 2026-05-11 的"严格不打扰": critical 健康告警 (致命药物交互/急性阈值)
必须穿透静默时段立即推送, 不能压到早上. 其余 severity 仍尊重 quiet-hours.
"""
import pytest

from app.services.notification.push_service import resolve_quiet_hours_policy


def test_critical_always_bypasses_quiet_hours_by_default():
    # 默认 respect_quiet_hours=True → 非 critical 会 delay; critical 穿透
    assert resolve_quiet_hours_policy("critical", None, True) == "bypass"


def test_critical_bypasses_even_when_caller_requested_delay():
    assert resolve_quiet_hours_policy("critical", "delay", True) == "bypass"


def test_critical_bypasses_even_when_caller_requested_drop():
    # 致命告警绝不能被 drop 掉
    assert resolve_quiet_hours_policy("critical", "drop", True) == "bypass"


@pytest.mark.parametrize("sev", ["info", "low", "warning", "medium", "high"])
def test_non_critical_respects_quiet_hours_delay(sev):
    assert resolve_quiet_hours_policy(sev, None, True) == "delay"


@pytest.mark.parametrize("sev", ["info", "low", "warning", "medium", "high"])
def test_non_critical_honours_explicit_policy(sev):
    assert resolve_quiet_hours_policy(sev, "bypass", True) == "bypass"
    assert resolve_quiet_hours_policy(sev, "drop", True) == "drop"


def test_respect_quiet_hours_false_maps_to_bypass_for_non_critical():
    assert resolve_quiet_hours_policy("warning", None, False) == "bypass"


def test_invalid_policy_raises():
    with pytest.raises(ValueError):
        resolve_quiet_hours_policy("high", "whenever", True)  # type: ignore[arg-type]
