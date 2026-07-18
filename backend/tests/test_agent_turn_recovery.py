from app.services.agent_turn_recovery import should_retry_tool_failure


def test_retries_transient_failure_for_read_tool_once():
    result = "Error: 健康数据查询执行失败，请稍后重试。"

    assert should_retry_tool_failure("health_query", result, attempt=0) is True
    assert should_retry_tool_failure("health_query", result, attempt=1) is False


def test_does_not_retry_write_tool_even_when_error_is_transient():
    result = "Error: 写入服务暂时不可用，请稍后重试。"

    assert should_retry_tool_failure("health_record", result, attempt=0) is False

def test_does_not_retry_deterministic_read_error():
    result = "Error: 未找到对应的健康记录。"

    assert should_retry_tool_failure("health_query", result, attempt=0) is False


def test_does_not_retry_confirmation_gate():
    result = "[NEEDS_CONFIRMATION] 我准备记录这条数据，请确认。"

    assert should_retry_tool_failure("health_record", result, attempt=0) is False
