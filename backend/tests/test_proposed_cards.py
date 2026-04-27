"""Specialist proposed_cards → ActionCard 落地 (信任循环)."""
from datetime import datetime

from app.orchestrator.orchestrator import _persist_proposed_cards
from app.orchestrator.schema import ProposedCard, SpecialistFinding
from app.models.action_card import ActionCard


def _finding(specialist_name: str, **card_overrides) -> SpecialistFinding:
    defaults = dict(
        title="测试卡片",
        content="...",
        metric_key="hrv",
        baseline_value="35",
        target_value=">42",
        verification_days=7,
    )
    defaults.update(card_overrides)
    return SpecialistFinding(
        specialist_name=specialist_name,
        category="recovery",
        proposed_cards=[ProposedCard(**defaults)],
    )


def test_persists_proposed_card(db):
    findings = [_finding("recovery_coach")]
    ids = _persist_proposed_cards(db, user_id=1, findings=findings)
    assert len(ids) == 1

    card = db.query(ActionCard).filter(ActionCard.id == ids[0]).one()
    assert card.creator_specialist == "recovery_coach"
    assert card.metric_key == "hrv"
    assert card.target_value == ">42"
    assert card.check_back_date is not None
    assert card.source_type == "orchestrator"


def test_dedupes_active_same_specialist_metric(db):
    """同 specialist + 同 metric + active → 只创建 1 张."""
    f1 = _finding("recovery_coach")
    f2 = _finding("recovery_coach")  # 同 metric_key=hrv

    ids1 = _persist_proposed_cards(db, user_id=1, findings=[f1])
    assert len(ids1) == 1

    ids2 = _persist_proposed_cards(db, user_id=1, findings=[f2])
    assert len(ids2) == 0  # 已存在 active, 跳过


def test_allows_different_metric_same_specialist(db):
    f1 = _finding("recovery_coach", metric_key="hrv")
    f2 = _finding("recovery_coach", metric_key="sleep_score", target_value=">75",
                  baseline_value="60")

    ids = _persist_proposed_cards(db, user_id=2, findings=[f1, f2])
    assert len(ids) == 2


def test_allows_same_metric_different_specialist(db):
    f1 = _finding("recovery_coach", metric_key="hrv")
    f2 = _finding("longitudinal_analyst", metric_key="hrv")

    ids = _persist_proposed_cards(db, user_id=3, findings=[f1, f2])
    assert len(ids) == 2


def test_recreates_after_archive(db):
    """老卡 archived 后, 同 specialist+metric 应可再建."""
    f = _finding("recovery_coach")
    ids1 = _persist_proposed_cards(db, user_id=4, findings=[f])
    assert len(ids1) == 1

    db.query(ActionCard).filter(ActionCard.id == ids1[0]).update({"status": "archived"})
    db.commit()

    ids2 = _persist_proposed_cards(db, user_id=4, findings=[f])
    assert len(ids2) == 1


class TestRecoveryCoachProposes:
    def test_low_readiness_with_hrv_drop_proposes_card(self):
        """端到端: HRV 下滑触发 RecoveryCoach 产 proposed_card."""
        from app.agents.recovery_coach.coach import RecoveryCoachSpecialist
        from app.twin.schema import HealthTwin, TwinMeta, PhysiologicalState

        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now()))
        twin.physiological = PhysiologicalState(
            hrv_latest=28.0,
            hrv_7d_avg=42.0,
            sleep_score_latest=55,
            stress_avg_today=60,
        )

        sp = RecoveryCoachSpecialist()
        finding = sp.run(twin, {})
        # 触发 HRV 回升 card
        assert len(finding.proposed_cards) >= 1
        c = finding.proposed_cards[0]
        assert c.metric_key == "hrv"
        assert c.target_value.startswith(">")
        assert c.baseline_value == "28"

    def test_high_readiness_no_card(self):
        from app.agents.recovery_coach.coach import RecoveryCoachSpecialist
        from app.twin.schema import HealthTwin, TwinMeta, PhysiologicalState

        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now()))
        twin.physiological = PhysiologicalState(
            hrv_latest=50.0, hrv_7d_avg=48.0, sleep_score_latest=85,
        )

        sp = RecoveryCoachSpecialist()
        finding = sp.run(twin, {})
        # 状态好不应产 card
        assert finding.proposed_cards == []


class TestHypertensionProposes:
    def test_stage1_proposes_bp_drop_card(self):
        from app.agents.chronic_specialists.hypertension import HypertensionSpecialist
        from app.twin.schema import HealthTwin, TwinMeta, LabsContext

        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now()))
        twin.labs = LabsContext(
            blood_pressure_systolic=140,
            blood_pressure_diastolic=92,
        )

        sp = HypertensionSpecialist()
        finding = sp.run(twin, {})
        cards = finding.proposed_cards
        assert len(cards) == 1
        assert cards[0].metric_key == "systolic_bp"
        assert cards[0].target_value.startswith("<")
        assert cards[0].baseline_value == "140"

    def test_normal_bp_no_card(self):
        from app.agents.chronic_specialists.hypertension import HypertensionSpecialist
        from app.twin.schema import HealthTwin, TwinMeta, LabsContext

        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now()))
        twin.labs = LabsContext(
            blood_pressure_systolic=118, blood_pressure_diastolic=75,
        )

        sp = HypertensionSpecialist()
        finding = sp.run(twin, {})
        assert finding.proposed_cards == []
