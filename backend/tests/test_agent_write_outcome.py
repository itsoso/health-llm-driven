import pytest

from app.services.agent_write_outcome import (
    classify_explicit_write_execution,
    classify_write_execution,
    is_legacy_local_write_rejection,
    local_write_rejection,
    result_declares_explicit_failure,
)


def test_structured_rejection_is_terminal_without_a_write_receipt():
    outcome = classify_write_execution({
        "status": "rejected",
        "error_code": "missing_required_field",
        "missing_fields": ["bedtime"],
        "dispatch_started": False,
    })

    assert outcome.status == "rejected"
    assert outcome.error_code == "missing_required_field"
    assert outcome.dispatch_started is False


def test_local_write_rejection_builds_one_stable_machine_contract():
    result = local_write_rejection(
        "missing_required_field",
        message="需要补充字段",
        recovery_guidance="补充后重试",
    )

    assert result == (
        '{"status":"rejected","success":false,"dispatch_started":false,'
        '"error_code":"missing_required_field","message":"需要补充字段",'
        '"recovery_guidance":"补充后重试"}'
    )
    outcome = classify_write_execution(result)
    assert outcome.status == "rejected"
    assert outcome.error_code == "missing_required_field"
    assert outcome.dispatch_started is False


@pytest.mark.parametrize(
    "error_code",
    ["", "UPPER_CASE", "has spaces", "contains/slash"],
)
def test_local_write_rejection_rejects_unstable_error_codes(error_code):
    with pytest.raises(ValueError, match="invalid_local_write_error_code"):
        local_write_rejection(error_code)


def test_structured_remote_uncertainty_does_not_become_rejected():
    outcome = classify_write_execution({
        "status": "uncertain",
        "error_code": "upstream_timeout",
        "dispatch_started": True,
    })

    assert outcome.status == "uncertain"
    assert outcome.error_code == "upstream_timeout"
    assert outcome.dispatch_started is True


def test_structured_confirmation_gate_is_a_failed_write_not_uncertain():
    outcome = classify_write_execution(
        '{"status":"needs_confirmation","error_code":"confirmation_required",'
        '"dispatch_started":false}'
    )

    assert outcome.status == "failed"
    assert outcome.error_code == "confirmation_required"
    assert outcome.dispatch_started is False


def test_verified_receipt_has_priority_over_result_text():
    outcome = classify_write_execution(
        "Error: upstream returned 500 after request dispatch",
        receipt={"operation_id": "health_record:diet_record:42", "verified": True},
    )

    assert outcome.status == "verified"
    assert outcome.receipt is not None


@pytest.mark.parametrize(
    "result",
    [
        "Error: 工具调用被策略拦截。tool=health_record; reason=write_tool_without_write_intent",
        "Error: 这段话不是明确的本人症状记录请求，已阻止自动写入。",
        "Error: 带附件的症状内容暂不自动写入，请在不带附件的消息中直接复述。",
        "Error: 症状记录参数无效，已阻止自动写入。",
    ],
)
def test_local_policy_and_symptom_guards_are_rejected_not_uncertain(result):
    outcome = classify_write_execution(result)

    assert outcome.status == "rejected"
    assert outcome.dispatch_started is False


def test_remote_api_error_with_local_marker_stays_uncertain():
    outcome = classify_write_execution(
        "Error: API 返回 500: 已阻止执行，请稍后重试。"
    )

    assert outcome.status == "uncertain"
    assert outcome.dispatch_started is None


def test_legacy_local_write_rejection_detection_excludes_structured_and_remote():
    assert is_legacy_local_write_rejection(
        "Error: diet 记录必须提供 food_items"
    ) is True
    assert is_legacy_local_write_rejection(
        local_write_rejection("diet_food_items_missing")
    ) is False
    assert is_legacy_local_write_rejection(
        "Error: API 返回 500: 必须提供 food_items"
    ) is False


def test_medication_plan_local_rejection_is_not_uncertain():
    outcome = classify_write_execution(
        "Error: 用药确认计划未能建立，本次没有写入。"
        "服务端未能封存完整的用药确认计划；"
        "请重新发送完整药名和本次实际服量。"
    )

    assert outcome.status == "rejected"
    assert outcome.dispatch_started is False


def test_legacy_needs_clarification_is_a_pre_dispatch_rejection():
    outcome = classify_write_execution(
        "[NEEDS_CLARIFICATION] 工具调用未执行。"
        "tool=health_record; reason=write_tool_without_write_intent"
    )

    assert outcome.status == "rejected"
    assert outcome.error_code == "policy_blocked"
    assert outcome.dispatch_started is False


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("cancelled", "rejected"),
        ("canceled", "rejected"),
        ("not_found", "rejected"),
        ("needs_confirmation", "failed"),
        ("uncertain", "uncertain"),
    ],
)
def test_explicit_structured_write_statuses_share_one_classifier(status, expected):
    outcome = classify_explicit_write_execution({"status": status})

    assert outcome is not None
    assert outcome.status == expected
    assert outcome.error_code == status


def test_payload_without_explicit_execution_status_is_not_misclassified():
    assert classify_explicit_write_execution({"id": 42}) is None


@pytest.mark.parametrize(
    "result",
    [
        {"status": "failed"},
        {"status": "rejected"},
        {"success": False},
        {"ok": False},
        {"error": "upstream unavailable"},
    ],
)
def test_explicit_failure_detector_accepts_only_hard_failures(result):
    assert result_declares_explicit_failure(result) is True


@pytest.mark.parametrize(
    "result",
    [
        {"status": "success"},
        {"status": "recorded"},
        {"status": "pending"},
        {"status": "processing"},
        {"status": "pending_user_confirmation"},
        {"id": 42},
    ],
)
def test_explicit_failure_detector_does_not_reject_nonterminal_or_success_states(
    result,
):
    assert result_declares_explicit_failure(result) is False
