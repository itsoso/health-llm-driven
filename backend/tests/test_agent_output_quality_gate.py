import pytest

from app.services.agent_output_quality import enforce_agent_output_quality


def test_normal_answer_is_preserved_byte_for_byte():
    answer = "## 结论\n\n今天优先恢复，明天再评估训练。"
    result = enforce_agent_output_quality(answer, max_chars=500)

    assert result.text == answer
    assert result.flags == ()


def test_oversized_answer_is_bounded_at_a_readable_section_boundary():
    answer = ("第一节。" * 80) + "\n\n" + ("第二节。" * 80)
    result = enforce_agent_output_quality(answer, max_chars=300)

    assert len(result.text) <= 300
    assert "已按段落截断" in result.text
    assert result.flags == ("persistence_budget_truncated",)
    assert result.original_length > result.persisted_length


def test_protocol_shaped_reply_is_rejected_instead_of_successful_prose():
    answer = '<tool_call>{"name":"health_query","arguments":{"dimension":"diet"}}</tool_call>\n正在查询。'
    result = enforce_agent_output_quality(answer)
    assert 'protocol_leak' in result.flags
    assert '<tool_call>' not in result.text
    assert '没有完成' in result.text


def test_documented_protocol_inside_code_is_not_a_tool_reply():
    answer = '格式示例：\n```xml\n<tool_call>example</tool_call>\n```\n这只是说明。'
    result = enforce_agent_output_quality(answer)
    assert result.text == answer
    assert not result.flags


@pytest.mark.parametrize("answer", [
    "Tool calls:\n- health_record",
    "工具调用：health_query",
    "要调用的工具：\n* health_query_batch",
    "tool_calls: synthetic_read",
])
def test_plaintext_tool_lists_are_nonempty_protocol_failures(answer):
    result = enforce_agent_output_quality(answer)
    assert result.flags == ("protocol_leak",)
    assert result.text.strip() and "没有完成" in result.text
    assert answer not in result.text


@pytest.mark.parametrize("answer", [
    "格式示例：\n```text\nTool calls:\n- health_query\n```\n这只是说明。",
    "示例 `工具调用：health_query` 不会执行。",
    "工具调用：用于按你的授权查询数据。",
    "health_query 是查询工具；本次没有执行它。",
])
def test_tool_documentation_remains_visible_without_false_protocol_failure(answer):
    result = enforce_agent_output_quality(answer)
    assert result.text == answer
    assert result.flags == ()
