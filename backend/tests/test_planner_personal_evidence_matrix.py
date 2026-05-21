from datetime import date, datetime, timedelta
import uuid

from app.orchestrator.orchestrator import _build_synthesis_prompt
from app.orchestrator.schema import SpecialistFinding
from app.twin.schema import (
    DataFreshness,
    EpigeneticState,
    GeneticContext,
    HealthTwin,
    LabsContext,
    PhysiologicalState,
    TwinMeta,
)


def _make_user(db):
    from app.models.user import User

    user = User(
        username=f"matrix_{uuid.uuid4().hex[:6]}",
        email=f"matrix_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="Matrix Planner User",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_daily_plan_prefers_lab_data_acquisition_when_lab_anchor_is_stale(db, monkeypatch):
    from app.services import daily_operating_plan as planner

    user = _make_user(db)
    twin = HealthTwin(
        meta=TwinMeta(user_id=user.id, generated_at=datetime(2026, 5, 21, 8, 0, 0)),
        labs=LabsContext(last_exam_date=date.today() - timedelta(days=180)),
        freshness=DataFreshness(labs="stale"),
    )
    monkeypatch.setattr(planner, "build_twin", lambda _db, _user_id, use_cache=False: twin)

    payload = planner.build_daily_operating_plan(db, user.id, plan_date=date.today())

    action_keys = [action["action_key"] for action in payload["actions"]]
    assert "measurement.update_lab_anchor" in action_keys
    assert action_keys.index("measurement.update_lab_anchor") < action_keys.index("nutrition.protein_target")
    assert not any(action["domain"] == "supplement" and action["confidence"] == "high" for action in payload["actions"])
    matrix = payload["state_summary"]["personal_evidence_matrix"]
    assert matrix["summary"]["by_signal_type"].get("lab", 0) == 0
    assert "lab_anchor_stale" in matrix["planner_flags"]


def test_daily_plan_downgrades_training_intensity_when_recovery_matrix_is_poor(db, monkeypatch):
    from app.services import daily_operating_plan as planner

    user = _make_user(db)
    twin = HealthTwin(
        meta=TwinMeta(user_id=user.id, generated_at=datetime(2026, 5, 21, 8, 0, 0)),
        physiological=PhysiologicalState(
            sleep_score_latest=58,
            hrv_status="low",
            training_readiness_score=None,
            last_updated=date.today(),
        ),
        freshness=DataFreshness(sleep="today"),
    )
    monkeypatch.setattr(planner, "build_twin", lambda _db, _user_id, use_cache=False: twin)

    payload = planner.build_daily_operating_plan(db, user.id, plan_date=date.today())

    movement_actions = [action for action in payload["actions"] if action["domain"] == "movement"]
    assert any(action["action_key"] == "movement.zone2_recovery" for action in movement_actions)
    assert not any(action["action_key"] == "movement.moderate_activity" for action in movement_actions)
    recovery_action = next(action for action in movement_actions if action["action_key"] == "movement.zone2_recovery")
    assert recovery_action["confidence"] == "medium"
    assert recovery_action["personal_evidence"]["trigger"] == "poor_recovery_matrix"


def test_orchestrator_prompt_keeps_genetic_only_associations_low_confidence():
    twin = HealthTwin(
        meta=TwinMeta(user_id=3, generated_at=datetime(2026, 5, 21, 8, 0, 0)),
        genetic=GeneticContext(
            has_profile=True,
            nutrition_variants=[{"gene_name": "MTHFR", "risk_level": "medium", "result_label": "叶酸代谢相关"}],
        ),
        freshness=DataFreshness(genetic="long_term"),
    )
    finding = SpecialistFinding(
        specialist_name="supplement_advisor",
        category="supplement",
        summary="MTHFR 相关叶酸建议",
        findings=[{"title": "考虑叶酸相关补剂", "action": "先补齐 Hcy/叶酸/B12 化验"}],
    )

    _, user_prompt = _build_synthesis_prompt("我需要补叶酸吗？", twin, [finding])

    assert "【个人证据矩阵】" in user_prompt
    assert "genetic_only_policy=low_until_validated" in user_prompt
    assert "gap.lab_anchor_missing" in user_prompt


def test_orchestrator_prompt_marks_epigenetic_as_long_term_proxy_only():
    twin = HealthTwin(
        meta=TwinMeta(user_id=3, generated_at=datetime(2026, 5, 21, 8, 0, 0)),
        epigenetic=EpigeneticState(
            has_methylation_report=True,
            status="present",
            latest_test_date="2026-05-01",
            clock_type="DunedinPACE",
            pace_of_aging=1.11,
            biological_age_delta_years=4.9,
        ),
        freshness=DataFreshness(epigenetic="long_term"),
    )
    finding = SpecialistFinding(
        specialist_name="longevity_coach",
        category="recovery",
        summary="甲基化报告提示长期趋势代理偏高",
        findings=[{"title": "8-12 周复测趋势", "action": "先执行睡眠、运动和代谢闭环"}],
    )

    _, user_prompt = _build_synthesis_prompt("我的生物年龄能逆转吗？", twin, [finding])

    assert "【个人证据矩阵】" in user_prompt
    assert "epigenetic_policy=long_term_proxy_only" in user_prompt
    assert "不能证明短期抗衰疗效" in user_prompt
    assert "epigenetic.pace_of_aging" in user_prompt
