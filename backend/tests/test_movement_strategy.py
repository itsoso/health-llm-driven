"""工作日微运动自适应策略(纯函数)测试。核心安全:Red 绝不出力量。"""
import pytest

from app.services.movement_strategy import (
    GRAY,
    GREEN,
    RED,
    TRIGGER_ARRIVAL,
    TRIGGER_HOURLY,
    TRIGGER_MEETING_GAP,
    TRIGGER_POST_LUNCH,
    TRIGGER_SEDENTARY,
    YELLOW,
    adapt_movement,
)

ALL_TRIGGERS = [
    TRIGGER_ARRIVAL, TRIGGER_SEDENTARY, TRIGGER_MEETING_GAP, TRIGGER_POST_LUNCH, TRIGGER_HOURLY,
]


@pytest.mark.parametrize("trigger", ALL_TRIGGERS)
def test_red_never_returns_strength(trigger):
    a = adapt_movement(RED, trigger=trigger)
    assert a["kind"] != "strength", "Red 灯绝不能出力量类动作"
    assert a["intensity"] == "recovery"


@pytest.mark.parametrize("trigger", ALL_TRIGGERS)
def test_red_ignores_pushup_preference(trigger):
    # 偏好俯卧撑也不能在 Red 下硬推力量(安全压过偏好)
    a = adapt_movement(RED, trigger=trigger, prefers_pushups=True)
    assert a["kind"] != "strength"


def test_green_sedentary_is_strength_standard():
    a = adapt_movement(GREEN, trigger=TRIGGER_SEDENTARY)
    assert a["kind"] == "strength" and a["intensity"] == "standard"


def test_green_post_lunch_is_walk():
    a = adapt_movement(GREEN, trigger=TRIGGER_POST_LUNCH)
    assert a["action_code"] == "walk"


def test_green_pushup_preference_honored():
    a = adapt_movement(GREEN, trigger=TRIGGER_HOURLY, prefers_pushups=True)
    assert a["action_code"] == "pushup" and a["intensity"] == "standard"


def test_yellow_downgrades_to_low_impact():
    a = adapt_movement(YELLOW, trigger=TRIGGER_SEDENTARY)
    assert a["intensity"] == "low"
    assert a["action_code"] != "squat" and a["action_code"] != "pushup"  # 标准力量被降级


def test_yellow_pushup_pref_becomes_incline():
    a = adapt_movement(YELLOW, trigger=TRIGGER_HOURLY, prefers_pushups=True)
    assert a["action_code"] == "incline_pushup" and a["intensity"] == "low"


def test_gray_is_conservative_with_note():
    a = adapt_movement(GRAY, trigger=TRIGGER_SEDENTARY)
    assert a["intensity"] == "low"
    assert "待同步" in a["rationale"]


def test_unknown_trigger_falls_back():
    a = adapt_movement(GREEN, trigger="bogus_trigger")
    assert a["kind"] == "strength"  # 退化为久坐打断默认


def test_none_light_treated_as_gray():
    a = adapt_movement(None, trigger=TRIGGER_SEDENTARY)
    assert a["intensity"] == "low" and "待同步" in a["rationale"]
