"""模型直接吐 record 裸 data(无 tool 包装)时,必须恢复成 health_record 调用
并写库,而不是把 JSON 当文本流给用户。

回归:聊天里"记录早餐:一杯豆浆 一块100克葱油饼" → glm-5 直接输出
{"record_date":...,"meal_type":"breakfast","food_items":...,"calories":400,...}
当可见消息(JSON 泄漏 + 饮食根本没写库)。
"""
import json

import pytest

from app.services.agent_executor import (
    _extract_inline_tool_call,
    _infer_record_type_from_payload,
    _loads_lenient,
    _repair_truncated_json,
    _strip_bracket_tool_markers,
)

_TOOLS = [
    {"type": "function", "function": {"name": "health_record"}},
    {"type": "function", "function": {"name": "health_query"}},
    {"type": "function", "function": {"name": "health_manage"}},
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
    # 真实场景带记录意图("记录早餐…")—— 裸对象推断成写入必须有明确记录意图门(防幽灵写)。
    recovered = _extract_inline_tool_call(
        text, _TOOLS, user_message="记录早餐:一杯豆浆 一块100克葱油饼")
    assert recovered is not None
    assert recovered["function"]["name"] == "health_record"
    args = json.loads(recovered["function"]["arguments"])
    assert args["record_type"] == "diet"
    assert args["data"]["food_items"].startswith("一杯豆浆")


def test_naked_record_object_without_intent_is_not_a_phantom_write():
    """只读问句("我体重多少")模型回显 {"weight":72.5} —— 无记录意图 → 绝不推断成
    health_record 写入(否则问句造幽灵/重复记录)。裸对象推断门必须要求明确记录意图。"""
    text = '你的体重是 {"weight":72.5,"record_date":"2026-07-17"}'
    # 无记录意图(纯查询)→ 不恢复成写入
    assert _extract_inline_tool_call(text, _TOOLS, user_message="我体重多少?") is None
    assert _extract_inline_tool_call(text, _TOOLS, user_message=None) is None
    # 有记录意图 → 恢复成 weight 写入
    got = _extract_inline_tool_call(text, _TOOLS, user_message="记录我体重72.5")
    assert got is not None and got["function"]["name"] == "health_record"


def test_flattened_sibling_args_not_dropped():
    """{"tool_name":"health_query","dimension":"diet","days":7}(参数平铺无容器)—— 此前
    dimension 被丢 → 默认 comprehensive 答错题。现在把 sibling 键当 args 保住。"""
    got = _extract_inline_tool_call(
        '{"tool_name":"health_query","dimension":"diet","days":7}',
        _TOOLS, user_message="查一下今天的饮食")
    assert got is not None and got["function"]["name"] == "health_query"
    args = json.loads(got["function"]["arguments"])
    assert args.get("dimension") == "diet" and args.get("days") == 7


def test_tool_input_container_recognized():
    """Anthropic 风格 tool_input 容器键也识别(此前只认 parameters/params/arguments/input/args)。"""
    got = _extract_inline_tool_call(
        '{"name":"health_query","tool_input":{"dimension":"sleep","days":7}}',
        _TOOLS, user_message="看看睡眠")
    assert got is not None and json.loads(got["function"]["arguments"]).get("dimension") == "sleep"


def test_named_tool_call_still_recovered():
    # 既有 name 包装的恢复不受影响
    text = '好的 {"name":"health_query","parameters":{"metric":"steps"}}'
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    assert recovered["function"]["name"] == "health_query"


def test_tool_code_tool_call_recovered():
    text = (
        '{"tool_code":"health_manage","arguments":{'
        '"record_type":"diet","operation":"list","date":"today",'
        '"meal_type":"breakfast"}}'
    )
    recovered = _extract_inline_tool_call(text, _TOOLS)
    assert recovered is not None
    assert recovered["function"]["name"] == "health_manage"
    args = json.loads(recovered["function"]["arguments"])
    assert args["record_type"] == "diet"
    assert args["operation"] == "list"


def test_naked_health_manage_args_are_not_misclassified_as_new_diet():
    text = (
        '{"record_type":"diet","operation":"list","date":"today",'
        '"meal_type":"breakfast"}'
    )

    recovered = _extract_inline_tool_call(
        text,
        _TOOLS,
        user_message="修改早餐：一碗小米粥 一个蔬菜饼",
    )

    assert recovered is not None
    assert recovered["function"]["name"] == "health_manage"
    args = json.loads(recovered["function"]["arguments"])
    assert args["record_type"] == "diet"
    assert args["operation"] == "list"
    assert _infer_record_type_from_payload(json.loads(text)) is None


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


# ── 弯引号/全角引号 JSON 兜底(glm-5.1 等弱模型)───────────────────────
def test_normalize_json_quotes_recovers_smart_quote_args():
    """弯引号/全角引号的工具参数 JSON,标准 json.loads 失败 → 归一后可解析。"""
    import json
    from app.services.agent_executor import _normalize_json_quotes

    # 模拟 glm-5.1 吐的(截图实拍):弯引号当分隔符
    bad = '{ “record_type”: “diet”, “data”: { “meal_type”: “lunch”, “food_items”: “虾仁 20个”, “calories”: 100 } }'
    import pytest
    with pytest.raises(json.JSONDecodeError):
        json.loads(bad)  # 标准解析必失败
    parsed = json.loads(_normalize_json_quotes(bad))  # 归一后成功
    assert parsed["record_type"] == "diet"
    assert parsed["data"]["meal_type"] == "lunch"
    assert parsed["data"]["food_items"] == "虾仁 20个"
    assert parsed["data"]["calories"] == 100


def test_normalize_json_quotes_noop_on_valid_json():
    """合法 JSON 不受影响(直引号原样)。"""
    import json
    from app.services.agent_executor import _normalize_json_quotes
    good = '{"record_type": "diet", "note": "正常文本"}'
    assert json.loads(_normalize_json_quotes(good)) == json.loads(good)


# ── 截断 JSON 兜底(glm-5.1 等弱模型把 tool args 切到一半)──────────────────
# 回归(截图实拍): 记"打喷嚏一次" → glm-5.1 吐
# {"record_type":"rhinitis","data":{"sneezing":1,"congestion":0,"runny_nose":0}
# 外层 } 缺失 → 标准解析失败 → "参数解析失败" 裸露给用户 + 鼻炎打卡丢失。
def test_repair_truncated_json_missing_outer_brace():
    bad = ('{"record_type": "rhinitis", "data": '
           '{"sneezing": 1, "congestion": 0, "runny_nose": 0}')
    with pytest.raises(json.JSONDecodeError):
        json.loads(bad)
    parsed = json.loads(_repair_truncated_json(bad))
    assert parsed["record_type"] == "rhinitis"
    assert parsed["data"]["sneezing"] == 1


def test_repair_truncated_json_trailing_comma_and_array():
    parsed = _loads_lenient('{"a": 1, "b": [1, 2, 3,')
    assert parsed == {"a": 1, "b": [1, 2, 3]}


def test_repair_truncated_json_unterminated_string():
    parsed = _loads_lenient('{"food_items": "虾仁 20')
    assert parsed["food_items"] == "虾仁 20"


def test_repair_truncated_json_noop_on_valid():
    # 完整 JSON 不被改动(无未闭合结构 → 原样返回)
    good = '{"record_type": "diet", "data": {"calories": 100}}'
    assert _repair_truncated_json(good) == good
    assert _loads_lenient(good) == json.loads(good)


def test_repair_does_not_invent_missing_value():
    # 截断在 key 后无值 → 修不出合法 JSON,_loads_lenient 必抛(不假装成功)
    with pytest.raises(json.JSONDecodeError):
        _loads_lenient('{"record_type": "rhinitis", "data": {"sneezing":')


def test_loads_lenient_smart_quotes_plus_truncation():
    # 弯引号 + 截断叠加: 归一+修复组合兜底
    bad = '{ “record_type”: “rhinitis”, “data”: { “sneezing”: 2'
    parsed = _loads_lenient(bad)
    assert parsed["record_type"] == "rhinitis"
    assert parsed["data"]["sneezing"] == 2


def test_inline_recovery_of_truncated_named_tool_call():
    # 整段是被截断的 named tool-call JSON(raw_decode 全失败)→ 截断修复后恢复
    text = ('{"name": "health_record", "parameters": '
            '{"record_type": "rhinitis", "data": {"sneezing": 1, "congestion": 0}')
    # 文本协议中的写调用必须同时有本轮明确记录意图；否则即使参数可修复也不能执行。
    assert _extract_inline_tool_call(text, _TOOLS, user_message=None) is None
    recovered = _extract_inline_tool_call(
        text,
        _TOOLS,
        user_message="记录鼻炎：打喷嚏 1 次，鼻塞 0",
    )
    assert recovered is not None
    assert recovered["function"]["name"] == "health_record"
    args = json.loads(recovered["function"]["arguments"])
    assert args["record_type"] == "rhinitis"
    assert args["data"]["sneezing"] == 1


# ── founder 2026-07-17 截图根因:tool_name-包装的工具调用泄漏 + 记录静默丢 ──────────
def test_recovers_tool_name_wrapped_symptom_call_from_leaked_text():
    """弱模型吐 {"tool_name":"health_record","arguments":{…}}(还嵌在 {"name":```json…}```
    fence 里),recovery 之前只认 name/tool 不认 tool_name → 症状没写库 + JSON 泄漏给用户。
    加 tool_name 后必须恢复成真 health_record 调用(既写库又不泄漏)。"""
    leaked = (
        '{\n  "name":```json\n'
        '{\n  "tool_name": "health_record",\n'
        '  "arguments": {\n    "record_type": "symptom",\n'
        '    "data": {\n      "description": "打喷嚏"\n    }\n  }\n}\n'
        '```已查到相关数据,但这轮没能整理成回答;请再问一次或换个问法。'
    )
    call = _extract_inline_tool_call(leaked, _TOOLS, user_message="记录刚才打了一个喷嚏。")
    assert call is not None, "tool_name-wrapped 调用必须被恢复, 不能泄漏成文本"
    assert call["function"]["name"] == "health_record"
    args = json.loads(call["function"]["arguments"])
    assert args["record_type"] == "symptom"
    assert args["data"]["description"] == "打喷嚏"


def test_recovers_plain_tool_name_query_call():
    """最小 tool_name shape(只读, 无需写授权):{"tool_name":"health_query","arguments":{…}}。"""
    call = _extract_inline_tool_call(
        '让我查一下。{"tool_name":"health_query","arguments":{"dimension":"diet"}}',
        _TOOLS, user_message="查一下今天的饮食",
    )
    assert call is not None and call["function"]["name"] == "health_query"
    assert json.loads(call["function"]["arguments"])["dimension"] == "diet"


def test_tool_name_still_gated_by_registered_allowlist():
    """tool_name 值不是已注册工具 → 不当调用恢复(不因加 tool_name 而误伤普通 JSON)。"""
    call = _extract_inline_tool_call(
        '{"tool_name":"send_email","arguments":{"to":"x"}}',
        _TOOLS, user_message="随便说说",
    )
    assert call is None
