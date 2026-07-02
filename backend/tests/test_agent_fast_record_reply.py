"""Fast-record reply builder must never dump raw created-record JSON at the user.

Regression for the chat bug where "记录打喷嚏一个" returned the raw symptom
record JSON ({"id":19,"body_part":"respiratory","description":"打喷嚏",...})
instead of a human confirmation.
"""
import json

from app.services.agent_executor import (
    _fast_record_reply_from_tool_results,
    _friendly_record_confirmation,
    _post_record_quality_response,
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
    assert reply == "已记录症状：打喷嚏（说「撤销」可删除）"  # 免确认前置后回显带撤销出口
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
    assert _friendly_record_confirmation({
        "title": "臀中肌训练",
        "remind_at": "2026-06-30T10:30:00+08:00",
        "recurrence": "daily",
    }) == "已设置每日提醒：臀中肌训练"
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


def test_diet_record_quality_response_uses_personal_context_and_next_action():
    response = _post_record_quality_response(
        "diet",
        {
            "meal_type": "lunch",
            "food_items": "煎牛肉能量碗, 水煮蛋, 姜黄鲜柠维C茶",
            "calories": 770,
            "protein": 30,
            "carbs": 70,
            "fat": 17,
        },
        personal_context="[用户健康档案]\n慢性病: 胃溃疡(Hp 阴性), 高血压\n健康目标: 每日饮水2000ml",
    )

    assert response is not None
    reply = response["reply"]
    assert "已记录午餐" in reply
    assert "蛋白" in reply and "30g" in reply
    assert "胃溃疡" in reply
    assert "酸" in reply or "冷" in reply
    assert "下一步" in reply
    assert "要不要算热量" not in reply
    assert "{" not in reply
    assert len(reply) <= 220

    assert response["cards"][0]["type"] == "record_quality"
    assert response["cards"][0]["data"]["domain"] == "diet"
    assert response["cards"][0]["actions"][0]["action"] == "route.open"


def test_exercise_record_quality_response_is_actionable_without_medical_claims():
    response = _post_record_quality_response(
        "exercise",
        {
            "exercise_type": "俯卧撑",
            "reps": 30,
            "sets": 3,
            "duration": 8,
        },
        personal_context="[用户健康档案]\n慢性病: 高血压\n",
    )

    assert response is not None
    reply = response["reply"]
    assert "已记录运动" in reply
    assert "俯卧撑" in reply
    assert "下一步" in reply
    assert "诊断" not in reply
    assert len(reply) <= 200
