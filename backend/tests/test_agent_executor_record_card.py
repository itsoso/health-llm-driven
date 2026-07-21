"""_health_record_card_descriptor: deterministic record card, never leaks raw JSON.

Regression: when the health_record tool returns a JSON dict WITHOUT a top-level
"message", the old fallback dumped the whole `{"record_date":...,"food_items":...}`
blob into the card detail (truncated with "..."), which surfaced as a raw-JSON
chat bubble. The fix synthesizes a clean summary from the structured args and
suppresses the card rather than ever rendering JSON.
"""

import json

import pytest

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


def test_reminder_summary_from_args():
    result = json.dumps({"id": 7, "title": "臀中肌训练", "recurrence": "daily"}, ensure_ascii=False)
    card = _health_record_card_descriptor(
        "reminder",
        {"title": "臀中肌训练", "recurrence": "daily", "remind_at": "2026-06-30T10:30:00+08:00"},
        result,
    )

    assert card is not None
    assert card["data"]["type"] == "reminder"
    assert card["data"]["detail"] == "已设置每日提醒：臀中肌训练"


def test_reminder_card_includes_honest_watch_delivery_boundary():
    result = json.dumps({
        "id": 7,
        "title": "喝水提醒",
        "recurrence": "daily",
        "delivery_status": {
            "agent_claim": "created_not_device_delivered",
            "iphone_notification": {
                "status": "will_attempt_when_due",
                "delivery_confirmed": False,
            },
            "watch": {
                "route": "watch_summary_due_item",
                "status": "visible_when_watch_summary_refreshes",
                "delivery_confirmed": False,
            },
        },
    }, ensure_ascii=False)

    card = _health_record_card_descriptor(
        "reminder",
        {"title": "喝水提醒", "recurrence": "daily", "remind_at": "2026-07-17T13:30:00+08:00"},
        result,
    )

    assert card is not None
    assert card["data"]["detail"] == (
        "已设置每日提醒：喝水提醒；手机到点会尝试提醒；"
        "手表刷新今日摘要后可执行（未确认已送达手表）"
    )
    assert "已发送到手表" not in card["data"]["detail"]
    assert "已同步到手表" not in card["data"]["detail"]


def test_error_result_returns_none():
    assert _health_record_card_descriptor("diet", {}, "Error: boom") is None


@pytest.mark.parametrize("status", ["rejected", "uncertain", "failed", "cancelled"])
def test_non_verified_structured_write_does_not_build_record_card(status):
    result = json.dumps(
        {
            "status": status,
            "dispatch_started": status == "uncertain",
            "message": "已记录晚餐：烤鱼",
        },
        ensure_ascii=False,
    )

    assert _health_record_card_descriptor(
        "diet",
        {"meal_type": "dinner", "food_items": "烤鱼"},
        result,
        write_verified=False,
    ) is None
