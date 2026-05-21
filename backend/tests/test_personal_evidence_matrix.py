from datetime import date, datetime

from app.services.personal_evidence_matrix import build_personal_evidence_matrix
from app.twin.schema import (
    BehavioralState,
    BodyCompositionState,
    DataFreshness,
    GeneticContext,
    HealthTwin,
    LabsContext,
    PhysiologicalState,
    TwinMeta,
)


def _signal_by_id(matrix, signal_id):
    return next(signal for signal in matrix["signals"] if signal["signal_id"] == signal_id)


def test_personal_evidence_matrix_normalizes_core_health_twin_signals():
    twin = HealthTwin(
        meta=TwinMeta(
            user_id=3,
            generated_at=datetime(2026, 5, 21, 8, 0, 0),
            data_sources=["genetic_report", "garmin", "body_measurement", "labs", "diet_log"],
        ),
        genetic=GeneticContext(
            has_profile=True,
            total_variants=2,
            risk_variants=[
                {"gene_name": "FTO", "risk_level": "high", "result_label": "肥胖倾向"},
            ],
            sleep_variants=[
                {"gene_name": "PER3", "risk_level": "medium", "result_label": "睡眠节律敏感"},
            ],
        ),
        labs=LabsContext(
            hba1c=5.9,
            ldl=3.7,
            blood_pressure_systolic=138,
            blood_pressure_diastolic=88,
            blood_pressure_date=date(2026, 5, 20),
            last_exam_date=date(2026, 5, 1),
        ),
        body_composition=BodyCompositionState(
            weight_kg=82.0,
            waist_cm=92.0,
            bmi=27.2,
            central_obesity_flag=True,
            last_weighed=date(2026, 5, 21),
            last_waist_measured=date(2026, 5, 21),
        ),
        physiological=PhysiologicalState(
            sleep_score_latest=62,
            sleep_duration_h_latest=5.8,
            hrv_latest=38,
            hrv_status="low",
            training_readiness_score=42,
            last_updated=date(2026, 5, 21),
        ),
        behavioral=BehavioralState(
            diet_calories_today=1850,
            diet_protein_g_today=95,
            meals_logged_today=3,
            water_ml_today=1600,
            workouts_this_week=2,
            acute_chronic_ratio=1.25,
        ),
        freshness=DataFreshness(
            genetic="long_term",
            labs="fresh",
            blood_pressure="fresh",
            weight="today",
            waist="today",
            sleep="today",
            diet="today",
        ),
    )

    matrix = build_personal_evidence_matrix(twin)

    assert matrix["user_id"] == 3
    assert matrix["summary"]["signal_count"] >= 6
    assert matrix["summary"]["by_signal_type"]["genetic"] >= 1
    assert matrix["summary"]["by_signal_type"]["lab"] >= 3
    assert matrix["summary"]["by_signal_type"]["body_measurement"] >= 3
    assert matrix["summary"]["by_signal_type"]["wearable"] >= 3
    assert matrix["summary"]["by_signal_type"]["behavior"] >= 3

    for signal in matrix["signals"]:
        assert signal["signal_id"]
        assert signal["signal_type"] in {
            "genetic",
            "lab",
            "body_measurement",
            "wearable",
            "behavior",
            "data_gap",
        }
        assert signal["freshness"] in {"today", "fresh", "recent", "stale", "long_term", "missing", "unknown"}
        assert signal["reliability"] in {"high", "medium", "low", "experimental"}
        assert isinstance(signal["domains"], list)
        assert signal["confidence_modifier"] in {"raise", "neutral", "lower"}

    hba1c = _signal_by_id(matrix, "lab.hba1c")
    assert hba1c["value"] == 5.9
    assert hba1c["freshness"] == "fresh"
    assert hba1c["reliability"] == "high"
    assert hba1c["domains"] == ["metabolic_health"]
    assert hba1c["confidence_modifier"] == "raise"

    sleep = _signal_by_id(matrix, "wearable.sleep_score_latest")
    assert sleep["value"] == 62
    assert sleep["domains"] == ["sleep", "recovery_capacity"]
    assert sleep["confidence_modifier"] == "raise"

    gene = _signal_by_id(matrix, "genetic.risk.FTO")
    assert gene["freshness"] == "long_term"
    assert gene["reliability"] == "medium"
    assert gene["confidence_modifier"] == "lower"


def test_personal_evidence_matrix_reports_missing_data_gaps_for_sparse_twin():
    twin = HealthTwin(meta=TwinMeta(user_id=3, generated_at=datetime(2026, 5, 21, 8, 0, 0)))

    matrix = build_personal_evidence_matrix(twin)

    gap_ids = {signal["signal_id"] for signal in matrix["signals"] if signal["signal_type"] == "data_gap"}
    assert {
        "gap.genetic_profile_missing",
        "gap.lab_anchor_missing",
        "gap.body_measurement_missing",
        "gap.wearable_sleep_recovery_missing",
        "gap.behavior_log_missing",
    }.issubset(gap_ids)
    assert matrix["summary"]["data_gap_count"] >= 5
    for gap in [signal for signal in matrix["signals"] if signal["signal_type"] == "data_gap"]:
        assert gap["freshness"] == "missing"
        assert gap["reliability"] == "low"
        assert gap["confidence_modifier"] == "lower"


def test_personal_evidence_matrix_accepts_plain_twin_dicts():
    matrix = build_personal_evidence_matrix(
        {
            "meta": {"user_id": 3, "generated_at": "2026-05-21T08:00:00"},
            "labs": {"uric_acid": 520, "last_exam_date": "2026-05-01"},
            "physiological": {"steps_today": 9000, "last_updated": "2026-05-21"},
            "freshness": {"labs": "fresh", "sleep": "today"},
        }
    )

    assert _signal_by_id(matrix, "lab.uric_acid")["value"] == 520
    assert _signal_by_id(matrix, "wearable.steps_today")["freshness"] == "today"
