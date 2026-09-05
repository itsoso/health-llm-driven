"""恢复文本形态的工具调用,同时拒绝执行任意伪代码。

覆盖 `<tool>funcname {args}</tool>` 与 founder 2026-07-16 截图中的
`<tool_code>print(health_record(...))</tool_code>`。后者只能在用户明确要求记录时恢复,
且只接受注册工具 + 纯字面量关键字参数。

现象: 模型把 health_query 写成 `<tool>health_query {"dimension":"water"}</tool>` 文本(而非
结构化 tool_calls)。既有恢复三路(invoke/bracket/JSON-with-name)都不认 → 工具**未执行**
(无水数据)+ 原始标记泄漏进显示。本 fix 让它被恢复成真调用: 执行(有数据)且不泄漏。
"""
import json

from app.services.agent_executor import (
    _XML_TOOLCALL_PREFIX_RE,
    _extract_inline_tool_call,
    _is_botched_text_tool_call,
    _strip_xml_tool_markers,
)

_TOOLS = [
    {"type": "function", "function": {"name": "health_record", "parameters": {}}},
    {"type": "function", "function": {"name": "health_query", "parameters": {}}},
    {"type": "function", "function": {"name": "health_manage", "parameters": {}}},
]


def _fn(text, *, user_message=None):
    r = _extract_inline_tool_call(text, _TOOLS, user_message=user_message)
    return r["function"] if r else None


def test_founder_water_leak_recovered_and_executable():
    # founder 截图确切串(带/不带尾空格)→ 恢复成 health_query 真调用
    for t in [
        '<tool>health_query {"dimension": "water"} </tool>',
        '<tool>health_query {"dimension": "water"}</tool>',
    ]:
        fn = _fn(t)
        assert fn is not None and fn["name"] == "health_query"
        assert '"water"' in fn["arguments"]


def test_recovered_with_prose_prefix():
    fn = _fn('好的,让我查一下 <tool>health_query {"dimension":"diet"}</tool>')
    assert fn and fn["name"] == "health_query"


def test_tool_call_and_function_call_tags():
    for tag in ("tool_call", "function_call", "tool"):
        fn = _fn(f'<{tag}>health_manage {{"record_type":"diet","operation":"list"}}</{tag}>')
        assert fn and fn["name"] == "health_manage"
        assert "diet" in fn["arguments"]


def test_nested_args_json_balanced():
    fn = _fn('<tool>health_manage {"record_type":"diet","data":{"meal_type":"breakfast"}}</tool>')
    assert fn and fn["name"] == "health_manage"
    assert "breakfast" in fn["arguments"]


def test_recovered_write_is_normal_health_manage_subject_to_confirm_gate():
    # belt-and-suspenders: 恢复的写调用 = 普通 health_manage delete 结构(name+operation+id),
    # 与原生结构化调用逐字节同形 → 下游确认门 source-agnostic, 恢复不绕过确认。
    fn = _fn(
        '<tool>health_manage {"record_type":"diet","operation":"delete","record_id":123}</tool>',
        user_message="删除记录 123",
    )
    assert fn is not None and fn["name"] == "health_manage"
    import json as _json
    args = _json.loads(fn["arguments"])
    assert args["operation"] == "delete" and args["record_id"] == 123
    # 恢复产物是无 provenance 的标准 function-call 形状(与 xml/bracket/json 恢复同形),
    # 无法夹带 confirmed=True 绕过门(args 里没有、也不会被下游当已确认)。
    assert "confirmed" not in args


def test_negatives_stay_visible():
    # 未注册工具名 / 无参数的文档示例 / 纯散文 → 不吞(保持可见, 不误执行)
    assert _fn('<tool>example</tool>') is None
    assert _fn('<tool>unknown_tool {"x":1}</tool>') is None
    assert _fn('see <tool> in the docs for {json} syntax') is None
    # 函数名后 { 不紧跟(相隔散文)→ 不当调用
    assert _fn('<tool>health_query</tool> 然后我会解释这个 {概念}') is None


def test_founder_sneeze_tool_code_print_is_recovered_as_real_record_call():
    text = """<tool_code>
print(health_record(record_type='symptom',
data={'description': '打喷嚏', 'body_part': 'respiratory'}))
</tool_code>"""

    fn = _fn(text, user_message="我准备睡觉了，记录刚才我打了一个喷嚏。")

    assert fn is not None and fn["name"] == "health_record"
    args = json.loads(fn["arguments"])
    assert args == {
        "record_type": "symptom",
        "data": {"description": "打喷嚏", "body_part": "respiratory"},
    }


def test_tool_code_health_record_requires_explicit_user_record_intent():
    text = (
        "<tool_code>print(health_record(record_type='symptom', "
        "data={'description': '打喷嚏'}))</tool_code>"
    )

    assert _fn(text, user_message="这段代码是什么意思？") is None
    assert _fn(text, user_message=None) is None


def test_tool_code_rejects_arbitrary_python_unknown_tools_and_positional_args():
    cases = (
        "<tool_code>import os; os.system('id')</tool_code>",
        "<tool_code>print(os.system('id'))</tool_code>",
        "<tool_code>print(unknown_tool(value=1))</tool_code>",
        "<tool_code>print(health_record('symptom', data={}))</tool_code>",
        "<tool_code>print(health_record(record_type=get_type(), data={}))</tool_code>",
        "<tool_code>print(health_record(record_type='symptom', data={'severity': 1e999}))</tool_code>",
    )

    for text in cases:
        assert _fn(text, user_message="记录一下") is None


def test_tool_code_inside_markdown_code_sample_is_not_executed_or_stripped():
    text = "```python\n<tool_code>print(health_record(record_type='symptom'))</tool_code>\n```"

    assert _fn(text, user_message="记录一下") is None
    assert _strip_xml_tool_markers(text) == text


def test_unparseable_tool_code_is_retryable_and_never_user_visible():
    text = "<tool_code>print(health_record(record_type='symptom', data=))</tool_code>"

    assert _fn(text, user_message="记录刚才打了一个喷嚏") is None
    assert _is_botched_text_tool_call(text, _TOOLS) is True
    assert _strip_xml_tool_markers(text) == ""


_FUNCTION_PARAMETER_RECORD_CALL = (
    "<tool_call>\n"
    "<function=health_record>\n"
    "<parameter=record_type> event </parameter>\n"
    '<parameter=data> {"title":"测试行程","occurred_at":"2026-09-05T17:33+08:00",'
    '"location":"测试地点","note":"测试备注"} </parameter>\n'
    "</function>\n"
    "</tool_call>"
)


def test_function_parameter_record_call_is_recovered_with_nested_data():
    """Provider XML dialect must become a real write instead of visible protocol text."""
    fn = _fn(_FUNCTION_PARAMETER_RECORD_CALL, user_message="记录行程")

    assert fn is not None and fn["name"] == "health_record"
    assert json.loads(fn["arguments"]) == {
        "record_type": "event",
        "data": {
            "title": "测试行程",
            "occurred_at": "2026-09-05T17:33+08:00",
            "location": "测试地点",
            "note": "测试备注",
        },
    }


def test_function_parameter_record_call_requires_explicit_write_intent():
    assert _fn(
        _FUNCTION_PARAMETER_RECORD_CALL,
        user_message="这段工具调用格式是什么意思？",
    ) is None
    assert _fn(
        _FUNCTION_PARAMETER_RECORD_CALL,
        user_message="不要记录行程",
    ) is None
    for question in ("记录行程？", "能记录行程吗？", "可以帮我记录行程吗？"):
        assert _fn(_FUNCTION_PARAMETER_RECORD_CALL, user_message=question) is None


def test_function_parameter_leak_is_retryable_and_never_user_visible():
    malformed = (
        "<tool_call><function=health_record>"
        "<parameter=record_type>event</parameter>"
        '<parameter=data>{"title":</parameter>'
    )

    assert _fn(malformed, user_message="记录行程") is None
    assert _is_botched_text_tool_call(malformed, _TOOLS) is True
    assert _strip_xml_tool_markers(malformed) == ""


def test_function_parameter_call_with_truncated_inner_parameter_is_not_executed():
    malformed = (
        "<tool_call><function=health_record>"
        "<parameter=record_type>event</parameter>"
        '<parameter=data>{"title":"测试行程"}'
        "</function></tool_call>"
    )

    assert _fn(malformed, user_message="记录行程") is None
    assert _is_botched_text_tool_call(malformed, _TOOLS) is True
    assert _strip_xml_tool_markers(malformed) == ""


def test_function_parameter_call_with_invalid_json_parameter_is_not_executed():
    malformed = (
        "<tool_call><function=health_record>"
        "<parameter=record_type>event</parameter>"
        '<parameter=data>{"title":}</parameter>'
        "</function></tool_call>"
    )

    assert _fn(malformed, user_message="记录行程") is None
    assert _is_botched_text_tool_call(malformed, _TOOLS) is True
    assert _strip_xml_tool_markers(malformed) == ""


def test_function_parameter_call_inside_markdown_code_is_not_executed_or_stripped():
    text = f"```xml\n{_FUNCTION_PARAMETER_RECORD_CALL}\n```"

    assert _fn(text, user_message="记录行程") is None
    assert _strip_xml_tool_markers(text) == text


def test_bare_function_parameter_protocol_is_never_user_visible():
    bare = (
        "<function=health_record>"
        "<parameter=record_type>event</parameter>"
        '<parameter=data>{"title":"测试行程"}</parameter>'
        "</function>"
    )

    assert _strip_xml_tool_markers(bare) == ""


def test_streaming_prefix_suppresses_bare_function_parameter_dialect():
    assert _XML_TOOLCALL_PREFIX_RE.search("<function=health_record>")
