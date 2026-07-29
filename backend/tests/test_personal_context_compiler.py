from datetime import UTC, datetime, timedelta
import inspect

import pytest

from app.services.health_evidence import (
    GapState,
    SafetyProfileContext,
    classify_health_intent,
    compile_personal_context,
)
from app.services.health_evidence.contracts import RiskLevel
from app.twin.schema import (
    AcuteHealthState,
    BehavioralState,
    ChronicConditionState,
    CrossSourceDivergence,
    DataFreshness,
    GeneticContext,
    HealthTwin,
    LabsContext,
    MedicationState,
    PhysiologicalState,
    ProblemRedLine,
    TwinMeta,
)


@pytest.fixture(autouse=True)
def _enable_health_evidence_runtime(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.health_evidence_runtime_enabled",
        True,
    )


NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
MANDATORY_LOW_BACK_CATEGORIES = {
    "symptom",
    "active_problem",
    "medication",
    "allergy",
    "chronic_condition",
}


def _rich_twin(*, failed_partitions=()) -> HealthTwin:
    return HealthTwin(
        meta=TwinMeta(
            user_id=7,
            generated_at=NOW,
            data_sources=["garmin", "medical_exam", "genetic", "diet"],
            failed_partitions=list(failed_partitions),
        ),
        physiological=PhysiologicalState(
            sleep_score_latest=61,
            hrv_latest=38,
            last_updated=NOW.date(),
            divergent_metrics=[
                CrossSourceDivergence(
                    metric="hrv",
                    label="HRV",
                    trusted_source="garmin",
                    outlier_source="ringconn",
                    deviation_pct=28.0,
                    hint="RingConn HRV 与 Garmin 明显偏离",
                )
            ],
        ),
        labs=LabsContext(hba1c=5.9, last_exam_date=NOW.date()),
        medication=MedicationState(
            has_any=True,
            active_meds=[
                {
                    "id": 991,
                    "name": "塞来昔布",
                    "dosage": "200mg",
                    "purpose": "疼痛",
                }
            ],
        ),
        genetic=GeneticContext(
            has_profile=True,
            total_variants=1,
            risk_variants=[
                {
                    "gene_name": "FTO",
                    "genotype": "AT",
                    "risk_level": "medium",
                    "result_label": "体重倾向",
                }
            ],
        ),
        behavioral=BehavioralState(
            diet_calories_today=1880,
            diet_protein_g_today=92,
            meals_logged_today=3,
        ),
        acute=AcuteHealthState(
            symptom_texts_all=["今早弯腰后腰痛"],
            problem_red_lines=[
                ProblemRedLine(
                    problem_name="腰痛",
                    condition="大小便异常或会阴麻木",
                    action="立即就医",
                    risk_level="P0",
                )
            ],
        ),
        chronic=ChronicConditionState(active_conditions=["胃溃疡"]),
        freshness=DataFreshness(
            sleep=NOW.date().isoformat(),
            labs=NOW.date().isoformat(),
            genetic="long_term",
            diet=NOW.date().isoformat(),
            medication=(NOW - timedelta(days=180)).date().isoformat(),
        ),
    )


def _compile(
    twin: HealthTwin,
    *,
    max_evidence_items: int = 8,
    allergies=("青霉素",),
):
    return compile_personal_context(
        twin=twin,
        intent=classify_health_intent("我腰疼怎么办"),
        safety_profile=SafetyProfileContext(allergies=allergies),
        max_evidence_items=max_evidence_items,
    )


def test_low_back_context_selects_safety_core_and_only_relevant_optional_evidence():
    packet = _compile(_rich_twin())
    categories = {item.category for item in packet.evidence}

    assert MANDATORY_LOW_BACK_CATEGORIES.issubset(categories)
    assert "wearable" in categories
    assert "lab" not in categories
    assert "genetic" not in categories
    assert "diet" not in categories


def test_every_mandatory_category_is_evidence_or_an_explicit_gap():
    sparse = HealthTwin(meta=TwinMeta(user_id=7, generated_at=NOW))
    packet = _compile(sparse, allergies=())
    evidence_categories = {item.category for item in packet.evidence}
    gap_categories = {gap.category for gap in packet.gaps}

    assert set(packet.mandatory_categories) == MANDATORY_LOW_BACK_CATEGORIES
    assert MANDATORY_LOW_BACK_CATEGORIES <= evidence_categories | gap_categories
    assert "symptom" in evidence_categories
    assert {
        "active_problem",
        "medication",
        "allergy",
        "chronic_condition",
    } <= gap_categories


def test_failed_partition_is_not_reported_as_absent_data():
    failed = _compile(_rich_twin(failed_partitions=("medication",)), allergies=())
    absent = _compile(
        HealthTwin(meta=TwinMeta(user_id=7, generated_at=NOW)),
        allergies=(),
    )

    failed_gap = next(g for g in failed.gaps if g.category == "medication")
    absent_gap = next(g for g in absent.gaps if g.category == "medication")
    assert failed_gap.state == GapState.FAILED
    assert failed_gap.failed_partition == "medication"
    assert absent_gap.state == GapState.ABSENT
    assert absent_gap.failed_partition is None


def test_budgeting_is_deterministic_and_never_drops_mandatory_categories():
    twin = _rich_twin()

    first = _compile(twin, max_evidence_items=7)
    second = _compile(twin, max_evidence_items=7)

    assert first == second
    assert len(first.evidence) <= 7
    assert first.budget.selected_items == len(first.evidence)
    assert first.budget.truncated is True
    assert MANDATORY_LOW_BACK_CATEGORIES <= {
        item.category for item in first.evidence
    } | {gap.category for gap in first.gaps}

    with pytest.raises(ValueError, match="mandatory"):
        _compile(twin, max_evidence_items=4)


def test_iso_freshness_is_normalized_against_frozen_twin_time():
    packet = _compile(_rich_twin())
    medication = next(item for item in packet.evidence if item.category == "medication")

    assert medication.freshness == "stale"
    assert medication.observed_at == (NOW - timedelta(days=180)).date().isoformat()


def test_cross_source_conflict_is_preserved_without_averaging_sources():
    packet = _compile(_rich_twin())

    assert len(packet.conflicts) == 1
    conflict = packet.conflicts[0]
    assert conflict.category == "wearable"
    assert conflict.trusted_source == "garmin"
    assert conflict.outlier_source == "ringconn"


def test_private_prompt_contains_values_but_public_manifest_does_not():
    packet = _compile(_rich_twin())

    private_prompt = packet.render_private_prompt()
    public_manifest = packet.to_public_manifest()
    public_json = public_manifest.model_dump_json()

    assert "塞来昔布" in private_prompt
    assert "青霉素" in private_prompt
    assert "胃溃疡" in private_prompt
    assert "塞来昔布" not in public_json
    assert "青霉素" not in public_json
    assert "胃溃疡" not in public_json
    assert "991" not in public_json
    assert "FTO" not in public_json
    assert public_manifest.evidence_refs
    assert set(public_manifest.context_categories_used) == {
        item.category for item in packet.evidence
    }


def test_public_projection_keeps_failed_vs_absent_but_hides_partition_names():
    packet = _compile(
        HealthTwin(
            meta=TwinMeta(
                user_id=7,
                generated_at=NOW,
                failed_partitions=["medication"],
            )
        ),
        allergies=(),
    )

    public = packet.to_public_manifest()
    public_json = public.model_dump_json()
    medication_gap = next(g for g in public.gaps if g.category == "medication")

    assert medication_gap.state == GapState.FAILED
    assert "failed_partition" not in public_json


def test_compiler_is_a_pure_twin_transform_without_a_database_parameter():
    params = inspect.signature(compile_personal_context).parameters

    assert "twin" in params
    assert "db" not in params
    assert _compile(_rich_twin()).evidence


def test_recent_twin_red_flag_is_compiled_as_private_emergency_signal():
    twin = HealthTwin(
        meta=TwinMeta(user_id=7, generated_at=NOW),
        acute=AcuteHealthState(
            symptom_texts_all=[
                "昨天开始腰痛",
                "今天排尿困难，而且会阴麻木",
            ],
        ),
    )
    frozen_before = twin.model_dump(mode="json")

    packet = _compile(twin, allergies=())

    assert twin.model_dump(mode="json") == frozen_before
    signal = next(
        item
        for item in packet.safety_signals
        if item.signal_id.startswith("guardian:symptoms.cauda_equina_warning")
    )
    assert signal.risk_level == RiskLevel.EMERGENCY
    assert signal.discriminator_id == "low_back.cauda_equina"
    assert "排尿" in signal.detail

    public = packet.to_public_manifest()
    public_json = public.model_dump_json()
    assert signal.signal_id in public.safety_signal_refs
    assert "排尿" not in public_json
    assert "会阴" not in public_json


def test_explicit_safety_profile_red_flag_is_preserved_without_public_detail():
    private_detail = "医生要求一旦腰痛伴既往肿瘤警示就尽快面诊"
    profile = SafetyProfileContext(
        risk_signals=(
            {
                "signal_id": "safety-profile:oncology-follow-up",
                "risk_level": RiskLevel.HIGH,
                "category": "safety_profile",
                "detail": private_detail,
                "source_kind": "safety_profile",
            },
        ),
    )

    packet = compile_personal_context(
        twin=HealthTwin(meta=TwinMeta(user_id=7, generated_at=NOW)),
        intent=classify_health_intent("我腰疼怎么办"),
        safety_profile=profile,
    )

    assert packet.safety_signals == profile.risk_signals
    public_json = packet.to_public_manifest().model_dump_json()
    assert "safety-profile:oncology-follow-up" in public_json
    assert private_detail not in public_json


def test_partial_guardian_evaluation_fails_closed_as_high_risk(
    monkeypatch,
):
    from app.agents.safety_guardian import engine

    monkeypatch.setattr(
        engine,
        "evaluate_rules_with_status",
        lambda _twin: ([], 1),
    )

    packet = _compile(
        HealthTwin(meta=TwinMeta(user_id=7, generated_at=NOW)),
        allergies=(),
    )

    signal = next(
        item
        for item in packet.safety_signals
        if item.signal_id == "guardian:safety.evaluation_incomplete"
    )
    assert signal.risk_level == RiskLevel.HIGH
    assert signal.source_kind == "safety_guardian"
