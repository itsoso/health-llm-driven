from app.services.agent_turn_recovery import (
    is_model_scope_refusal,
    should_buffer_refusal_response,
    should_retry_tool_failure,
)


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


def test_model_scope_refusal_is_recoverable_but_safety_refusal_is_not():
    assert is_model_scope_refusal("抱歉，我只能记录数据，无法提供分析和建议。") is True
    assert is_model_scope_refusal("抱歉，我无法提供诊断或处方建议。") is False


def test_apology_prefixed_answer_is_buffered_before_final_classification():
    assert should_buffer_refusal_response("抱歉，") is True
    assert should_buffer_refusal_response("我建议你先查询最近 7 天的睡眠数据。") is False
