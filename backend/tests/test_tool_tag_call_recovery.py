"""恢复 `<tool>funcname {args}</tool>` 形态的工具调用 — 修 founder 2026-07-14「列出喝水记录」。

现象: 模型把 health_query 写成 `<tool>health_query {"dimension":"water"}</tool>` 文本(而非
结构化 tool_calls)。既有恢复三路(invoke/bracket/JSON-with-name)都不认 → 工具**未执行**
(无水数据)+ 原始标记泄漏进显示。本 fix 让它被恢复成真调用: 执行(有数据)且不泄漏。
"""
from app.services.agent_executor import _extract_inline_tool_call

_TOOLS = [
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
