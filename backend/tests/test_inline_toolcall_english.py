"""内联工具调用:英文 [tool_call: ...] 标记的恢复 + 剥离 + 无引号 dict 解析。

实测 bug(用户截图):Claude-Opus-4.7 经代理吐
  [tool_call: health_record(type=diet, data={meal_type: "snack", food_items: "牛肉 150g...", calories: 530, protein: 48, carbs: 55, fat: 14, fiber: 2})]
旧正则只认中文「工具调用」→ 既没恢复执行(记录没真写库=假装成功)又没剥离(裸 JSON 泄漏)。
"""
import json

from app.services.agent_executor import (
    _extract_bracket_tool_call,
    _strip_bracket_tool_markers,
    _coerce_bracket_value,
    _parse_bracket_tool_args,
)

_SCREENSHOT = (
    '我帮你记录这次加餐 🍖🍜\n\n'
    '[tool_call: health_record(type=diet, data={meal_type: "snack", '
    'food_items: "牛肉 150g + 半份面条(约100g生重)", calories: 530, '
    'protein: 48, carbs: 55, fat: 14, fiber: 2})]'
)
_ALLOWED = {"health_record", "health_query"}


def test_english_tool_call_recovered():
    call = _extract_bracket_tool_call(_SCREENSHOT, _ALLOWED)
    assert call is not None
    assert call["function"]["name"] == "health_record"
    args = json.loads(call["function"]["arguments"])
    # type 别名 + data 无引号 key 应解析成真 dict
    assert args.get("type") == "diet"
    assert isinstance(args.get("data"), dict)
    assert args["data"]["meal_type"] == "snack"
    assert args["data"]["calories"] == 530


def test_english_tool_call_stripped_from_display():
    out = _strip_bracket_tool_markers(_SCREENSHOT)
    assert "tool_call" not in out and "health_record" not in out
    assert "我帮你记录这次加餐" in out  # 正文保留


def test_chinese_marker_still_works():
    txt = '已记录 [工具调用: health_query(dimension=medical_exam)]'
    call = _extract_bracket_tool_call(txt, _ALLOWED)
    assert call and call["function"]["name"] == "health_query"
    assert "工具调用" not in _strip_bracket_tool_markers(txt)


def test_coerce_unquoted_key_dict():
    d = _coerce_bracket_value('{meal_type: "snack", calories: 530}')
    assert isinstance(d, dict) and d["meal_type"] == "snack" and d["calories"] == 530


def test_coerce_smart_quotes_dict():
    # 弯引号 dict 也救
    d = _coerce_bracket_value('{“k”: “v”}')
    assert isinstance(d, dict) and d.get("k") == "v"


def test_parse_args_keeps_nested_data():
    args = _parse_bracket_tool_args('type=diet, data={meal_type: "snack", calories: 530}')
    assert args["type"] == "diet" and isinstance(args["data"], dict)
    assert args["data"]["calories"] == 530


def test_non_tool_json_not_stripped():
    # menu_share 等非工具 JSON 不应被误剥(无 tool_call 标记)
    txt = '今晚吃这些 ```menu_share\n{"title":"晚餐"}\n```'
    assert _strip_bracket_tool_markers(txt) == txt
