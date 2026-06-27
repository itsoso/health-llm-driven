"""Chronic-condition diet boundary reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

DIET_CHRONIC_CLAIMS = {
    "diabetes_low_carb": "claim:c_diet_diabetes_extreme_carb_restriction_boundary",
    "ckd_protein": "claim:c_diet_ckd_protein_extreme_boundary",
    "gout_fast_weight_loss": "claim:c_diet_gout_crash_diet_dehydration_boundary",
    "hypertension_potassium_salt": "claim:c_diet_hypertension_potassium_salt_ckd_boundary",
}

DIET_CHRONIC_CONTRAINDICATIONS = {
    "diabetes_low_carb": "contraindication:diet_diabetes_no_extreme_carb_or_fasting",
    "ckd_protein": "contraindication:diet_ckd_no_high_protein_or_zero_protein",
    "gout_fast_weight_loss": "contraindication:diet_gout_no_crash_diet_or_dehydration",
    "hypertension_potassium_salt": "contraindication:diet_hypertension_no_potassium_salt_without_review",
}

DIET_CHRONIC_EVALS = {
    "diabetes_low_carb": "eval:diet_diabetes_extreme_carb_boundary",
    "ckd_protein": "eval:diet_ckd_protein_boundary",
    "gout_fast_weight_loss": "eval:diet_gout_crash_diet_boundary",
    "hypertension_potassium_salt": "eval:diet_hypertension_potassium_salt_boundary",
}


def _claim(doc_id: str) -> dict[str, Any]:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _twin(
    *,
    conditions: list[str] | None = None,
    hba1c: float | None = None,
    egfr: float | None = None,
    uric_acid: float | None = None,
    systolic_bp: int | None = None,
    protein_g: float | None = None,
    carbs_g: float | None = None,
    medications: list[dict[str, Any]] | None = None,
):
    from app.twin.schema import (
        BehavioralState,
        ChronicConditionState,
        HealthTwin,
        LabsContext,
        MedicationState,
        TwinMeta,
    )

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 6, 27, tzinfo=UTC)))
    twin.chronic = ChronicConditionState(active_conditions=conditions or [])
    twin.labs = LabsContext(
        hba1c=hba1c,
        egfr=egfr,
        uric_acid=uric_acid,
        blood_pressure_systolic=systolic_bp,
    )
    twin.behavioral = BehavioralState(
        diet_protein_g_today=protein_g,
        diet_carbs_g_today=carbs_g,
    )
    twin.medication = MedicationState(active_meds=medications or [])
    return twin


def _claim_ids_for_twin(db, twin) -> set[str]:
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    payload = system_kb_twin_payload_from_health_twin(twin)
    result = lookup_for_twin(db, payload)
    return {claim.get("doc_id") for claim in result.get("claims") or []}


def _condition_claim_ids_for_twin(db, twin) -> set[str]:
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    payload = system_kb_twin_payload_from_health_twin(twin)
    result = lookup_for_twin(db, payload)
    return {
        claim.get("doc_id")
        for claim in result.get("claims") or []
        if claim.get("match_type") == "condition"
    }


def test_diet_chronic_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_chronic_import")
    assert counts["skipped_documents"] == 0

    doc_ids = (
        set(DIET_CHRONIC_CLAIMS.values())
        | set(DIET_CHRONIC_CONTRAINDICATIONS.values())
        | set(DIET_CHRONIC_EVALS.values())
    )
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in DIET_CHRONIC_CLAIMS.values():
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in DIET_CHRONIC_CONTRAINDICATIONS.values():
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in DIET_CHRONIC_EVALS.values():
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_diabetes_extreme_carb_lookup_uses_mapped_carbs_and_glycemic_context(db):
    from app.services.system_knowledge_service import system_kb_twin_payload_from_health_twin

    import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_diabetes_lookup")

    risky = _twin(conditions=["2型糖尿病"], hba1c=8.1, carbs_g=35)
    payload = system_kb_twin_payload_from_health_twin(risky)
    assert payload["behavioral"]["diet_carbs_g_today"] == 35
    assert DIET_CHRONIC_CLAIMS["diabetes_low_carb"] in _condition_claim_ids_for_twin(
        db, risky
    )

    moderate = _twin(conditions=["2型糖尿病"], hba1c=8.1, carbs_g=145)
    assert DIET_CHRONIC_CLAIMS["diabetes_low_carb"] not in _condition_claim_ids_for_twin(
        db, moderate
    )


def test_ckd_protein_lookup_requires_kidney_context_and_high_protein(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_ckd_lookup")

    risky = _twin(conditions=["慢性肾病"], egfr=52, protein_g=135)
    assert DIET_CHRONIC_CLAIMS["ckd_protein"] in _condition_claim_ids_for_twin(db, risky)

    normal_kidney = _twin(conditions=["增肌"], egfr=92, protein_g=135)
    assert DIET_CHRONIC_CLAIMS["ckd_protein"] not in _condition_claim_ids_for_twin(
        db, normal_kidney
    )


def test_gout_crash_diet_lookup_requires_uric_acid_or_gout_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_gout_lookup")

    risky = _twin(conditions=["痛风"], uric_acid=510, carbs_g=40)
    assert DIET_CHRONIC_CLAIMS["gout_fast_weight_loss"] in _condition_claim_ids_for_twin(
        db, risky
    )

    no_gout = _twin(conditions=["减脂"], uric_acid=310, carbs_g=40)
    assert DIET_CHRONIC_CLAIMS["gout_fast_weight_loss"] not in _condition_claim_ids_for_twin(
        db, no_gout
    )


def test_hypertension_potassium_salt_lookup_requires_kidney_or_potassium_med_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_hypertension_potassium_lookup")

    risky = _twin(
        conditions=["高血压"],
        egfr=55,
        systolic_bp=142,
        medications=[{"name": "losartan", "generic_name": "losartan"}],
    )
    assert DIET_CHRONIC_CLAIMS["hypertension_potassium_salt"] in _condition_claim_ids_for_twin(
        db, risky
    )

    plain_high_bp = _twin(conditions=["高血压"], egfr=90, systolic_bp=142)
    assert DIET_CHRONIC_CLAIMS["hypertension_potassium_salt"] not in _condition_claim_ids_for_twin(
        db, plain_high_bp
    )


def test_system_kb_eval_runner_covers_diet_chronic_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_chronic_eval")

    report = run_system_kb_eval_cases(db, case_ids=set(DIET_CHRONIC_EVALS.values()))

    assert report["total"] == 4
    assert report["failed"] == 0, report
    assert {case["case_id"] for case in report["cases"]} == set(DIET_CHRONIC_EVALS.values())


def test_diet_chronic_claims_keep_actions_inside_clinician_boundary():
    for doc_id in DIET_CHRONIC_CLAIMS.values():
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("医生", "营养师", "复核", "边界")), doc_id
        for banned in [
            "必须断食",
            "必须生酮",
            "完全不吃主食",
            "完全不吃蛋白",
            "完全不吃盐",
            "自行调整胰岛素",
            "停用胰岛素",
            "降压药减半",
            "大量喝水",
            "诊断为",
            "确诊",
        ]:
            assert banned not in blob, f"{doc_id} 越界: {banned}"
