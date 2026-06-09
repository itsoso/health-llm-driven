"""模型直接吐 record 裸 data(无 tool 包装)时,必须恢复成 health_record 调用
并写库,而不是把 JSON 当文本流给用户。

回归:聊天里"记录早餐:一杯豆浆 一块100克葱油饼" → glm-5 直接输出
{"record_date":...,"meal_type":"breakfast","food_items":...,"calories":400,...}
当可见消息(JSON 泄漏 + 饮食根本没写库)。
"""
import json

from app.services.agent_executor import (
    _extract_inline_tool_call,
    _infer_record_type_from_payload,
)

_TOOLS = [
    {"type": "function", "function": {"name": "health_record"}},
    {"type": "function", "function": {"name": "health_query"}},
]


def test_infer_diet_from_naked_payload():
    payload = {"record_date": "2026-06-09", "meal_type": "breakfast",
               "food_items": "一杯豆浆 + 葱油饼 100克", "calories": 400.0}
    assert _infer_record_type_from_payload(payload) == "diet"


def test_infer_other_record_types():
    assert _infer_record_type_from_payload({"systolic": 120, "diastolic": 80}) == "blood_pressure"
    assert _infer_record_type_from_payload({"exercise_type": "跑步", "reps": 0}) == "exercise"
    assert _infer_record_type_from_payload({"amount": 250, "drink_type": "水"}) == "water"
    assert _infer_record_type_from_payload({"weight": 71.2}) == "weight"
    assert _infer_record_type_from_payload({"description": "头痛", "severity": 3}) == "symptom"


def test_infer_returns_none_for_non_record_json():
    # 普通 JSON(如分享菜单)不应被误判成 record
    assert _infer_record_type_from_payload({"menu": ["A", "B"], "title": "今日推荐"}) is None
    assert _infer_record_type_from_payload({"record_date": "2026-06-09"}) is None


def test_naked_diet_json_recovered_as_health_record_call():
    text = ('{"record_date":"2026-06-09","meal_type":"breakfast",'
            '"food_items":"一杯豆浆 + 葱油饼 100克","calories":400.0,'
            '"protein":13.0,"carbs":46.0,"fat":19.0}')
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    assert recovered["function"]["name"] == "health_record"
    args = json.loads(recovered["function"]["arguments"])
    assert args["record_type"] == "diet"
    assert args["data"]["food_items"].startswith("一杯豆浆")


def test_named_tool_call_still_recovered():
    # 既有 name 包装的恢复不受影响
    text = '好的 {"name":"health_query","parameters":{"metric":"steps"}}'
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    assert recovered["function"]["name"] == "health_query"


def test_plain_text_not_treated_as_tool_call():
    assert _extract_inline_tool_call("你今天血压偏高,建议休息。", _TOOLS) is None
