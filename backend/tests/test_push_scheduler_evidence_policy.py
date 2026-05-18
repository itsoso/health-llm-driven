from app.services.notification.push_scheduler import build_health_alert_push_data


def test_health_alert_push_data_marks_safety_alert_as_supported_boundary():
    data = build_health_alert_push_data({"type": "poor_sleep"})

    assert data["alert_type"] == "poor_sleep"
    assert data["support_status"] == "safety_alert"
    assert data["unsupported"] is False
    assert data["unsupported_reason"] is None
    assert data["evidence_ref_count"] == 0
    assert data["evidence_refs"] == []
    assert data["planner_evidence_policy"]["blocked"] is False
    assert data["planner_evidence_policy"]["kept_reason"] == "safety_or_data_gap"
    assert "不替代医生" in data["claim_boundary"]


def test_health_alert_push_data_adds_rule_identity_for_dedup_and_opt_out():
    data = build_health_alert_push_data({"type": "high_stress"})

    assert data["rule_id"] == "wearable.high_stress"
    assert data["rule_source"] == "push_scheduler.wearable_threshold"
    assert data["evidence_domain"] == "recovery_stress"
