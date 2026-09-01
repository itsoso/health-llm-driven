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
