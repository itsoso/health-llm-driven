from app.services.agent_executor import _source_labels_from_system_prompt


def test_source_labels_include_memory_only_when_memory_context_is_injected():
    assert _source_labels_from_system_prompt(
        "基础提示\n\n## 用户记忆\n- 用户晚餐后容易反酸"
    ) == ["用户记忆"]
    assert _source_labels_from_system_prompt(
        "基础提示\n\n请不要在正文里声称使用了用户记忆"
    ) == []


def test_source_labels_include_lite_prompt_history_memory_heading():
    assert _source_labels_from_system_prompt(
        "基础提示\n\n用户历史记忆:\n- 午餐偏好清淡"
    ) == ["用户记忆"]
