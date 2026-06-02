"""Fast-record reply builder must never dump raw created-record JSON at the user.

Regression for the chat bug where "记录打喷嚏一个" returned the raw symptom
record JSON ({"id":19,"body_part":"respiratory","description":"打喷嚏",...})
instead of a human confirmation.
"""
import json

from app.services.agent_executor import (
    _fast_record_reply_from_tool_results,
    _friendly_record_confirmation,
)


def _tool_msg(payload) -> dict:
    return {"role": "tool", "content": json.dumps(payload, ensure_ascii=False)}


def test_symptom_record_json_becomes_friendly_line_not_raw_json():
    record = {
        "id": 19,
        "user_id": 3,
        "occurred_at": "2026-06-02T11:31:13.455118+08:00",
        "body_part": "respiratory",
        "description": "打喷嚏",
        "severity": 1,
        "triggers": [],
        "duration_minutes": None,
    }
    reply = _fast_record_reply_from_tool_results([_tool_msg(record)])
    assert reply == "已记录症状：打喷嚏"
    assert "{" not in reply and "body_part" not in reply


def test_explicit_message_field_is_preferred():
    reply = _fast_record_reply_from_tool_results([_tool_msg({"message": "已记录饮水 250ml"})])
    assert reply == "已记录饮水 250ml"


def test_friendly_confirmation_covers_common_record_shapes():
    assert _friendly_record_confirmation({"systolic": 120, "diastolic": 80}) == "已记录血压 120/80 mmHg"
    assert _friendly_record_confirmation({"food_items": "牛肉面"}) == "已记录饮食：牛肉面"
    assert _friendly_record_confirmation({"weight": 71.2}) == "已记录体重 71.2 kg"
    assert _friendly_record_confirmation({"exercise_type": "俯卧撑", "reps": 20}) == "已记录运动：俯卧撑 20 次"
    assert _friendly_record_confirmation({"glucose_mg_dl": 99.1}) == "已记录血糖 99.1 mg/dL"
    assert _friendly_record_confirmation({"mood_score": 8}) == "已记录心情 8/10"
    # Unknown shape → safe generic, never raw JSON.
    assert _friendly_record_confirmation({"id": 1, "foo": "bar"}) == "✅ 已记录"


def test_batch_array_result_confirms_count_not_json():
    reply = _fast_record_reply_from_tool_results([_tool_msg([{"id": 1}, {"id": 2}])])
    assert reply == "✅ 已记录 2 条"


def test_plain_text_tool_result_passes_through():
    msg = {"role": "tool", "content": "未找到名为 '维生素X' 的活跃补剂"}
    reply = _fast_record_reply_from_tool_results([msg])
    assert reply == "未找到名为 '维生素X' 的活跃补剂"


def test_error_tool_result_passes_through():
    msg = {"role": "tool", "content": "Error: water amount 必须是整数毫升"}
    reply = _fast_record_reply_from_tool_results([msg])
    assert reply.startswith("Error")
