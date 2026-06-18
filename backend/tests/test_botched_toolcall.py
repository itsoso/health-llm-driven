"""文本式工具调用检测 + 剥离(Claude-via-proxy 偶发把工具调用写成 Markdown 文本)。"""
from app.services.agent_executor import _is_botched_text_tool_call, _strip_text_tool_call, _extract_inline_tool_call

TOOLS = [{"function": {"name": "health_query"}}, {"function": {"name": "health_record"}}]


def test_detects_markdown_toolcall():
    # 生产实测的确切失败文本
    c = "我帮你拉一下完整补剂库。\n\nTool calls:\n- health_query"
    assert _is_botched_text_tool_call(c, TOOLS) is True
    # 这种无参数格式 _extract_inline_tool_call 解析不出(才需要重提示)
    assert _extract_inline_tool_call(c, TOOLS) is None


def test_detects_chinese_marker():
    assert _is_botched_text_tool_call("工具调用:\n- health_record", TOOLS) is True


def test_no_false_positive_on_normal_answer():
    # 正常回复:没标题标记 → 不算
    assert _is_botched_text_tool_call("你的补剂库有 6 项:维生素D、鱼油……", TOOLS) is False
    # 提了标记词但没命名已注册工具 → 不算
    assert _is_botched_text_tool_call("Tool calls: 暂无需要调用的", TOOLS) is False


def test_strip_removes_marker():
    c = "我帮你拉一下完整补剂库。\n\nTool calls:\n- health_query"
    assert _strip_text_tool_call(c) == "我帮你拉一下完整补剂库。"
    assert "Tool calls" not in _strip_text_tool_call(c)
