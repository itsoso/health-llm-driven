from app.services.agent_turn_outcome import classify_agent_turn_outcome


def test_success_outcome_is_explicit_when_a_write_receipt_exists():
    result = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="已记录晚餐，并完成今天的营养分析。",
        write_receipts=[{"operation_id": "health_record:1", "verified": True}],
    )

    assert result == {
        "status": "complete",
        "category": "success",
        "reason_code": "verified_write",
        "retryable": False,
        "dispatch_started": False,
        "verified_receipt_count": 1,
        "actions": [],
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
    assert result["retryable"] is False


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


def test_runtime_control_unavailable_is_terminal_and_not_immediately_retryable():
    result = classify_agent_turn_outcome(
        completion_status="error",
        final_text="记录服务当前处于保护性暂停状态，这次没有写入。",
        tool_failure_tools=["health_record"],
        runtime_control_unavailable=True,
    )

    assert result["category"] == "service_unavailable"
    assert result["reason_code"] == "runtime_control_unavailable"
    assert result["retryable"] is False
    assert result["refusal_detected"] is False


def test_unverified_write_requires_reconciliation_and_is_never_retryable():
    result = classify_agent_turn_outcome(
        completion_status="error",
        final_text="本次记录请求的状态暂时无法确认。",
        tool_failure_tools=["health_record"],
        write_reconciliation_required=True,
    )

    assert result["category"] == "write_reconciliation_required"
    assert result["reason_code"] == "missing_receipt"
    assert result["retryable"] is False
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
    assert result["status"] == "waiting_for_user"


def test_outcome_envelope_keeps_block_failure_and_refusal_statuses_distinct():
    blocked = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="本轮没有执行。",
        capability_block_reasons=["write_tool_without_write_intent"],
    )
    failed = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="查询失败。",
        tool_failure_tools=["health_query"],
    )
    refused = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="抱歉，我只能记录数据，无法提供分析和建议。",
    )

    assert blocked["status"] == "blocked"
    assert failed["status"] == "failed"
    assert refused["status"] == "refused"


def test_claimed_multi_action_write_requires_one_verified_receipt_per_action():
    result = classify_agent_turn_outcome(
        completion_status="complete",
        final_text="第一项已记录，第二项状态待核对。",
        write_receipts=[{"operation_id": "health_record:1", "verified": True}],
        claimed_write_action_count=2,
        dispatch_started=True,
        action_outcomes=[
            {
                "action_id": "health_record:1",
                "status": "verified",
                "receipt_verified": True,
                "dispatch_started": True,
            },
            {
                "action_id": "health_record:2",
                "status": "reconciliation_required",
                "reason_code": "missing_receipt",
                "receipt_verified": False,
                "dispatch_started": True,
                "recovery_guidance": "请先核对记录状态，不要重复提交。",
            },
        ],
    )

    assert result["status"] == "reconciliation_required"
    assert result["retryable"] is False
    assert result["dispatch_started"] is True
    assert result["verified_receipt_count"] == 1
    assert [action["status"] for action in result["actions"]] == [
        "verified",
        "reconciliation_required",
    ]


def test_failure_after_write_dispatch_is_not_blindly_retryable():
    result = classify_agent_turn_outcome(
        completion_status="error",
        final_text="写入状态暂时无法确认。",
        tool_failure_tools=["health_record"],
        dispatch_started=True,
    )

    assert result["status"] == "reconciliation_required"
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


def test_failed_action_cannot_be_hidden_by_an_unrelated_verified_action():
    result = classify_agent_turn_outcome(
        completion_status='complete', final_text='第一项完成，第二项未完成。',
        write_receipts=[{'verified': True, 'resource_id': 'synthetic'}],
        action_outcomes=[{'status': 'verified'}, {'status': 'rejected', 'reason_code': 'wrong_domain'}],
    )
    assert result['status'] != 'complete'
    assert result['retryable'] is False
    assert result['reason_code'] == 'wrong_domain'


def test_unresolved_action_requires_reconciliation_even_without_redundant_flags():
    result = classify_agent_turn_outcome(
        completion_status='complete', final_text='状态核对中。',
        action_outcomes=[{'status': 'reconciliation_required', 'reason_code': 'missing_receipt'}],
    )
    assert result['status'] == 'reconciliation_required'
    assert result['retryable'] is False


def test_output_protocol_failure_cannot_be_successful():
    result = classify_agent_turn_outcome(
        completion_status='complete', final_text='这次没有完成，请重试。',
        output_quality_flags=['protocol_leak'],
    )
    assert result['status'] == 'failed'
    assert result['reason_code'] == 'protocol_leak'


def test_action_display_limit_does_not_hide_later_failure():
    result = classify_agent_turn_outcome(
        completion_status='complete', final_text='处理完成。',
        action_outcomes=[{'status':'verified'} for _ in range(32)] + [{'status':'failed', 'reason_code':'late_failure'}],
    )
    assert result['status'] == 'failed'
    assert result['reason_code'] == 'late_failure'


def test_mixed_failure_and_waiting_does_not_depend_on_action_order():
    first = {'status':'waiting_for_user'}
    second = {'status':'failed', 'reason_code':'write_failed'}
    results = [classify_agent_turn_outcome(completion_status='complete', final_text='待处理', action_outcomes=items)
               for items in ([first, second], [second, first])]
    assert results[0]['status'] == results[1]['status'] == 'failed'


def test_medical_hold_does_not_count_as_an_answered_advice_task():
    result = classify_agent_turn_outcome(
        completion_status='complete', final_text='该建议需要先核验。',
        medical_boundary_flags=['unverified_dose_action'],
    )
    assert result['status'] == 'blocked'
    assert result['category'] == 'medical_evidence_required'
    assert result['retryable'] is False


def test_partial_query_preserves_verified_goal_without_claiming_whole_task_success():
    result = classify_agent_turn_outcome(
        completion_status="complete", final_text="已查到睡眠，本次未查到血氧。",
        capability_block_reasons=["semantics_unresolved"],
        goal_outcomes=[
            {"goal_id": "sleep", "kind": "query", "status": "verified", "evidence_kind": "read_result"},
            {"goal_id": "oxygen", "kind": "query", "status": "rejected", "reason_code": "semantics_unresolved"},
        ],
    )
    assert result["status"] == "partial"
    assert result["reason_code"] == "partial_goal_completion"
    assert result["retryable"] is False
    assert [goal["status"] for goal in result["goals"]] == ["verified", "rejected"]


def test_existing_read_result_cannot_verify_requested_sync():
    result = classify_agent_turn_outcome(
        completion_status="complete", final_text="系统里已经有昨天的数据。",
        goal_outcomes=[
            {"goal_id": "sync", "kind": "sync", "status": "verified", "evidence_kind": "read_result"},
        ],
    )
    assert result["status"] == "failed"
    assert result["reason_code"] == "missing_goal_evidence"


def test_goal_confirmation_and_uncertainty_override_partial_success():
    for pending, expected in [("waiting_for_user", "waiting_for_user"), ("reconciliation_required", "reconciliation_required")]:
        result = classify_agent_turn_outcome(
            completion_status="complete", final_text="查询完成，写入还需确认。",
            goal_outcomes=[
                {"goal_id": "sleep", "kind": "query", "status": "verified", "evidence_kind": "read_result"},
                {"goal_id": "record", "kind": "write", "status": pending},
            ],
        )
        assert result["status"] == expected
        assert result["retryable"] is False


def test_task_completion_metadata_preserves_generation_and_marks_failed_action():
    from app.services.agent_turn_outcome import agent_completion_metadata

    for status in ("failed", "blocked", "refused", "partial", "reconciliation_required"):
        assert agent_completion_metadata("complete", {"status": status}) == {
            "generation_status": "complete", "completion_status": "error",
        }
    assert agent_completion_metadata("complete", {"status": "waiting_for_user"}) == {
        "generation_status": "complete", "completion_status": "complete",
    }
    assert agent_completion_metadata("interrupted", {"status": "failed"}) == {
        "generation_status": "interrupted", "completion_status": "interrupted",
    }


def test_partial_results_do_not_override_medical_or_protocol_safety():
    goals = [
        {"goal_id": "sleep", "kind": "query", "status": "verified", "evidence_kind": "read_result"},
        {"goal_id": "oxygen", "kind": "query", "status": "failed"},
    ]
    for flags, expected in [
        ({"medical_boundary_flags": ["unsupported_claim"]}, "medical_evidence_required"),
        ({"output_quality_flags": ["protocol_leak"]}, "protocol_leak"),
    ]:
        result = classify_agent_turn_outcome(
            completion_status="complete", final_text="部分数据已读取。",
            goal_outcomes=goals, **flags,
        )
        assert result["reason_code"] == expected
        assert result["status"] != "partial"
