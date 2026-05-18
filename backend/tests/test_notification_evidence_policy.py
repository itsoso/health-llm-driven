from app.services.notification.evidence_policy import build_notification_evidence_data


def test_ai_advice_without_refs_is_marked_model_inference_unsupported():
    data = build_notification_evidence_data(
        notification_type="ai_advice",
        source="agent_loop",
        existing_data={"source": "agent_loop"},
    )

    assert data["source"] == "agent_loop"
    assert data["support_status"] == "model_inference"
    assert data["unsupported"] is True
    assert data["unsupported_reason"] == "missing_system_kb_evidence_refs"
    assert data["evidence_ref_count"] == 0
    assert data["evidence_refs"] == []
    assert "不替代医生" in data["claim_boundary"]


def test_trend_report_without_refs_is_data_summary_not_unsupported():
    data = build_notification_evidence_data(
        notification_type="trend_report",
        source="notifications.send_trend_morning_push",
    )

    assert data["support_status"] == "data_summary"
    assert data["unsupported"] is False
    assert data["unsupported_reason"] is None
    assert data["planner_evidence_policy"]["kept_reason"] == "data_summary"


def test_action_card_followup_inherits_card_evidence_refs():
    data = build_notification_evidence_data(
        notification_type="ai_advice",
        source="notifications.check_action_card_followups",
        existing_data={"card_id": 12},
        evidence_refs=["claim:c_recovery_low_reduce_intensity"],
        evidence_domain="training_recovery",
    )

    assert data["card_id"] == 12
    assert data["support_status"] == "supported"
    assert data["unsupported"] is False
    assert data["evidence_ref_count"] == 1
    assert data["evidence_refs"] == ["claim:c_recovery_low_reduce_intensity"]
    assert data["evidence_domain"] == "training_recovery"
