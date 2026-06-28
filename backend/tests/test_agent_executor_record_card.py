"""_health_record_card_descriptor: deterministic record card, never leaks raw JSON.

Regression: when the health_record tool returns a JSON dict WITHOUT a top-level
"message", the old fallback dumped the whole `{"record_date":...,"food_items":...}`
blob into the card detail (truncated with "..."), which surfaced as a raw-JSON
chat bubble. The fix synthesizes a clean summary from the structured args and
suppresses the card rather than ever rendering JSON.
"""

import json

from app.services.agent_executor import _health_record_card_descriptor


def test_diet_result_without_message_uses_clean_summary_not_json():
    record_data = {
        "record_date": "2026-06-28",
        "meal_type": "dinner",
        "meal_time": None,
        "food_items": "馒头 100g + 咸鸭蛋 2个 + 西红柿 1个 + 虾仁 15个",
    }
    # Tool result is a JSON dict with NO "message" field — the bug trigger.
    result = json.dumps(record_data, ensure_ascii=False)

    card = _health_record_card_descriptor("diet", record_data, result)

    assert card is not None
    detail = card["data"]["detail"]
    assert "{" not in detail and "record_date" not in detail  # no raw JSON leak
    assert "晚餐" in detail and "馒头 100g" in detail
    assert card["data"]["type"] == "diet"


def test_message_field_still_preferred():
    record_data = {"meal_type": "lunch", "food_items": "沙拉"}
    result = json.dumps({"message": "已记录午餐：沙拉一份"}, ensure_ascii=False)
    card = _health_record_card_descriptor("diet", record_data, result)
    assert card["data"]["detail"] == "已记录午餐：沙拉一份"


def test_json_result_no_message_no_usable_args_suppresses_card():
    # Unknown-shaped JSON with nothing presentable → no card, never raw JSON.
    result = json.dumps({"record_date": "2026-06-28", "foo": "bar"}, ensure_ascii=False)
    card = _health_record_card_descriptor("exercise", {"foo": "bar"}, result)
    assert card is None


def test_plain_text_result_first_line_still_used():
    card = _health_record_card_descriptor("water", {}, "已记录饮水 250ml\n额外说明")
    assert card["data"]["detail"] == "已记录饮水 250ml"


def test_water_summary_from_args():
    result = json.dumps({"amount": 2000}, ensure_ascii=False)
    card = _health_record_card_descriptor("water", {"amount": 2000}, result)
    assert card["data"]["detail"] == "已记录饮水 2000ml"


def test_blood_pressure_summary_from_args():
    result = json.dumps({"systolic": 119, "diastolic": 75}, ensure_ascii=False)
    card = _health_record_card_descriptor(
        "blood_pressure", {"systolic": 119, "diastolic": 75}, result
    )
    assert "119/75" in card["data"]["detail"]


def test_error_result_returns_none():
    assert _health_record_card_descriptor("diet", {}, "Error: boom") is None
