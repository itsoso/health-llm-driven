"""Deterministic numeric floor for acute vital readings in user text.

A turn that *states* an acute vital value ("记一下血压185/115") must never be
treated as a casual/fast record turn: it gets the high-stakes answer tier (quality
model + full prompt). Thresholds mirror the SafetyGuardian acute rules so the
routing floor and the post-write alert agree on what "acute" means.
"""
import pytest

from app.services.llm.acute_vitals import acute_vital_reading


@pytest.mark.parametrize(
    "message,expected",
    [
        # Blood pressure: systolic >= 180 or diastolic >= 120 (vitals.bp_severe_reading)
        ("记一下血压185/115", "bp_severe"),
        ("血压 190/100", "bp_severe"),
        ("记录血压150/125", "bp_severe"),
        ("血压185／115mmHg", "bp_severe"),
        ("血压185 115", "bp_severe"),
        ("血压：185-115", "bp_severe"),
        ("BP 182/96", "bp_severe"),
        ("bp182/96", "bp_severe"),
        ("早上量了 185/100 mmHg", "bp_severe"),
        ("记录收缩压185 舒张压110", "bp_severe"),
        ("高压185低压115", "bp_severe"),
        ("低压125", "bp_severe"),
        ("今天9/30，血压185/115", "bp_severe"),
        ("血压185,115", "bp_severe"),
        ("量了血压185，110", "bp_severe"),
        ("记录bp185/110", "bp_severe"),
        # SpO2 < 90 (spo2 severe/mild hypoxia boundary; < 88 is CRITICAL)
        ("记录血氧85", "spo2_low"),
        ("血氧饱和度 86%", "spo2_low"),
        ("SpO2 84", "spo2_low"),
        ("spo2:89%", "spo2_low"),
        # Heart rate: < 40 always; >= 130 outside exercise context
        ("记一下心率35", "hr_extreme"),
        ("静息心率135", "hr_extreme"),
        ("心率 140 次/分", "hr_extreme"),
        ("没运动，心率150", "hr_extreme"),
        ("心率150，没有跑步", "hr_extreme"),
        # Glucose: severe hypo / hyperglycaemic crisis range
        ("记一下血糖2.5", "glucose_extreme"),
        ("血糖 3.0 mmol/L", "glucose_extreme"),
        ("血糖 25.3", "glucose_extreme"),
        ("血糖 350 mg/dL", "glucose_extreme"),
        ("血糖45mg/dl", "glucose_extreme"),
        # Temperature
        ("体温40度", "temperature_extreme"),
        ("体温 39.6℃", "temperature_extreme"),
        ("体温34.5", "temperature_extreme"),
    ],
)
def test_acute_vital_readings_are_detected(message, expected):
    assert acute_vital_reading(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "",
        None,
        "记一下血压120/80",
        "血压135/85",
        "血压 179/119",
        "今天9/30",
        "9/30 记一下血压 120/80",
        "查一下我最近的血压",
        "为什么我最近血压偏高",
        "记一下体重180斤",
        "今天走了18000步",
        "记录血氧97",
        "血氧 95%",
        "心率 72",
        "跑步时心率150",
        "训练最大心率185",
        "骑车平均心率 142",
        "记一下血糖5.6",
        "血糖 110 mg/dL",
        "体温36.8",
        "喝了500ml水",
        "睡了7.5小时",
        "高血压家族史",
        "血压计是180块买的",
    ],
)
def test_normal_or_non_vital_text_is_not_floored(message):
    assert acute_vital_reading(message) is None


@pytest.mark.parametrize(
    "message",
    [
        "记一下血压185/115",
        "血压 190/100",
        "记录收缩压185 舒张压110",
        "高压185低压115",
        "记一下心率35",
        "体温40度",
    ],
)
def test_acute_vital_turns_classify_high_stakes(message):
    from app.services.llm.task_routing import classify_answer_task_tier

    assert classify_answer_task_tier(message, has_attachments=False) == "high_stakes"


@pytest.mark.parametrize(
    "message,expected",
    [
        ("记一下血压120/80", "casual"),
        ("血压135/85", "casual"),
    ],
)
def test_normal_vital_records_keep_their_tier(message, expected):
    from app.services.llm.task_routing import classify_answer_task_tier

    assert classify_answer_task_tier(message, has_attachments=False) == expected


def test_acute_vital_record_is_not_fast_eligible_even_as_a_write():
    from app.services.agent_executor import _is_fast_eligible_turn

    assert _is_fast_eligible_turn("记一下血压185/115", has_images=False, has_file=False) is False
    assert _is_fast_eligible_turn("记一下心率35", has_images=False, has_file=False) is False
    # Regression: normal readings stay on the fast record path.
    assert _is_fast_eligible_turn("记一下血压120/80", has_images=False, has_file=False) is True
