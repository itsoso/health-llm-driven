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
    _strip_bracket_tool_markers,
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


# ── 括号 + Python 调用签名格式: `[工具调用: name(args)]` ──────────────────
# 回归: 某些经代理的模型把工具调用吐成这种自然语言标记而非结构化 tool_calls,
# executor 不认 → 不执行 + 裸标记泄漏给用户 (用户截图: 助手正文显示
# `[工具调用: health_query(type=lab_results, keywords=["同型半胱氨酸"], days=7)]`)。


def test_bracket_format_recovered_with_args():
    text = ('[工具调用: health_query(type=lab_results, '
            'keywords=["Hcy","B12"], days=7)]')
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    assert recovered["function"]["name"] == "health_query"
    args = json.loads(recovered["function"]["arguments"])
    assert args["type"] == "lab_results"          # 裸标识符 → 字符串
    assert args["keywords"] == ["Hcy", "B12"]      # JSON 数组
    assert args["days"] == 7                        # 数字


def test_bracket_format_chinese_colon():
    text = '[工具调用：health_query(type=lab_results, days=30)]'
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    assert recovered["function"]["name"] == "health_query"
    args = json.loads(recovered["function"]["arguments"])
    assert args["type"] == "lab_results"
    assert args["days"] == 30


def test_bracket_format_no_brackets():
    # 方括号可选 — 裸 `工具调用: name(args)` 也认
    text = '工具调用: health_query(indicator="LDL")'
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    args = json.loads(recovered["function"]["arguments"])
    assert args["indicator"] == "LDL"              # 带引号字符串去引号


def test_bracket_format_surrounded_by_prose():
    text = '我来帮你查一下化验结果。[工具调用: health_query(type=lab_results, days=7)] 稍等。'
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    assert recovered["function"]["name"] == "health_query"


def test_bracket_format_unknown_name_not_recovered():
    # name 不在 allowed → 不认 (返回 None),不误执行
    text = '[工具调用: not_a_real_tool(foo=bar)]'
    assert _extract_inline_tool_call(text, _TOOLS) is None


def test_bracket_format_no_args():
    text = '[工具调用: health_query()]'
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    assert json.loads(recovered["function"]["arguments"]) == {}


def test_bracket_format_unparseable_arg_skipped_name_kept():
    # 健壮容错: 解析不出的参数跳过,至少恢复 name + 能解析的参数
    text = '[工具调用: health_query(type=lab_results, broken=, days=7)]'
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    args = json.loads(recovered["function"]["arguments"])
    assert args["type"] == "lab_results"
    assert args["days"] == 7
    assert "broken" not in args


def test_strip_bracket_markers_unknown_name():
    # 即便没解析出 tool call (name 不在白名单),最终输出也要剥离裸标记
    text = '这是分析结果。[工具调用: mystery_tool(x=1)] 完成。'
    stripped = _strip_bracket_tool_markers(text)
    assert "工具调用" not in stripped
    assert "这是分析结果" in stripped


def test_strip_bracket_markers_noop_without_marker():
    text = '你今天血压偏高,建议休息。'
    assert _strip_bracket_tool_markers(text) == text
