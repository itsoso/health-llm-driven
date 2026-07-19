from app.services.agent_write_outcome import classify_write_execution


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
