from app.services.agent_turn_outcome import classify_agent_turn_outcome


def test_success_outcome_is_explicit_when_a_write_receipt_exists():
    result = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="已记录晚餐，并完成今天的营养分析。",
        write_receipts=[{"operation_id": "health_record:1"}],
    )

    assert result == {
        "category": "success",
        "reason_code": "verified_write",
        "retryable": False,
        "refusal_detected": False,
        "capability_block_count": 0,
        "tool_failure_count": 0,
        "confirmation_required": False,
    }


def test_capability_block_is_not_reported_as_a_model_refusal():
    result = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="暂时无法完成这次记录。",
        capability_block_reasons=["write_tool_without_write_intent"],
    )

    assert result["category"] == "tool_blocked"
    assert result["reason_code"] == "write_tool_without_write_intent"
    assert result["refusal_detected"] is False
    assert result["retryable"] is True


def test_tool_failure_is_retryable_and_keeps_refusal_metric_false():
    result = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="这次请求没有完成，请稍后重试。",
        tool_failure_tools=["health_query"],
    )

    assert result["category"] == "tool_failed"
    assert result["reason_code"] == "health_query"
    assert result["retryable"] is True
    assert result["refusal_detected"] is False


def test_confirmation_is_distinct_from_failure():
    result = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="请确认后保存这条饮食记录。",
        pending_confirmation_tools=["health_record"],
    )

    assert result["category"] == "confirmation_required"
    assert result["reason_code"] == "health_record"
    assert result["confirmation_required"] is True
    assert result["retryable"] is False


def test_short_scope_refusal_is_detected_without_flagging_safe_boundary_text():
    refusal = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="抱歉，我无法提供具体诊断或处方建议。",
    )
    safe_boundary = classify_agent_turn_outcome(
        completion_status="complete",
        final_text=(
            "我不能替代医生诊断；如果症状持续或加重，建议尽快就医，"
            "我可以帮你整理需要观察的变化。"
        ),
    )

    assert refusal["category"] == "safety_refusal"
    assert refusal["reason_code"] == "safety_boundary"
    assert refusal["refusal_detected"] is True
    assert safe_boundary["category"] == "success"
    assert safe_boundary["refusal_detected"] is False


def test_model_scope_refusal_is_distinct_from_safety_refusal():
    result = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="抱歉，我只能记录数据，无法提供分析和建议。",
    )

    assert result["category"] == "model_refusal"
    assert result["reason_code"] == "model_scope"
    assert result["retryable"] is True


def test_completion_error_wins_over_error_shaped_model_text():
    result = classify_agent_turn_outcome(
        completion_status="error",
        final_text="抱歉，我无法完成这次请求。",
    )

    assert result["category"] == "execution_error"
    assert result["reason_code"] == "completion_error"
    assert result["refusal_detected"] is False


def test_write_without_tool_is_action_not_executed():
    result = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="我还没有记下来。",
        record_intent_no_tool=True,
    )

    assert result["category"] == "action_not_executed"
    assert result["reason_code"] == "write_without_tool"
    assert result["retryable"] is True
