from datetime import date

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.services.notification.evidence_policy import (
    build_notification_evidence_data,
    build_notification_evidence_data_for_user,
)
from tests.test_system_knowledge_phase0 import _seed_phase0_knowledge


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


def test_ai_advice_for_user_attaches_system_kb_refs_from_twin(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    profile = GeneticProfile(
        user_id=user.id,
        test_provider="wegene",
        test_date=date(2026, 5, 1),
    )
    db.add(profile)
    db.flush()
    db.add(
        GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            rsid="rs1801133",
            category="nutrition",
            gene_name="MTHFR",
            variant_name="C677T",
            genotype="TT",
            result_label="叶酸代谢显著减弱",
            risk_level="high",
            variant_nature="risk",
        )
    )
    db.commit()

    data = build_notification_evidence_data_for_user(
        db,
        user_id=user.id,
        notification_type="ai_advice",
        source="agent_loop",
        existing_data={"source": "agent_loop"},
    )

    assert data["support_status"] == "supported"
    assert data["unsupported"] is False
    assert data["unsupported_reason"] is None
    assert data["evidence_refs"] == ["claim:c_mthfr_c677t_hcy_folate_boundary"]
    assert data["planner_evidence_policy"]["kept_reason"] == "supported"
