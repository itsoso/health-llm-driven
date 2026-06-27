"""Supplement safety reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

SUPPLEMENT_CLAIMS = {
    "vitamin_d": "claim:c_supplement_vitamin_d_ckd_calcium_boundary",
    "magnesium": "claim:c_supplement_magnesium_absorption_renal_boundary",
    "omega3": "claim:c_supplement_omega3_bleeding_medication_boundary",
    "caffeine": "claim:c_supplement_caffeine_sleep_stimulant_boundary",
    "probiotic": "claim:c_supplement_probiotic_immunocompromised_boundary",
    "melatonin": "claim:c_supplement_melatonin_sedative_boundary",
    "st_johns_wort": "claim:c_supplement_st_johns_wort_medication_interaction_boundary",
}

SUPPLEMENT_CONTRAINDICATIONS = {
    "vitamin_d": "contraindication:supplement_vitamin_d_no_high_dose_ckd",
    "magnesium": "contraindication:supplement_magnesium_no_self_manage_low_egfr_or_absorption_meds",
    "omega3": "contraindication:supplement_omega3_no_self_manage_bleeding_stack",
    "caffeine": "contraindication:supplement_caffeine_no_sleep_rescue_or_stimulant_escalation",
    "probiotic": "contraindication:supplement_probiotic_no_self_use_immunocompromised",
    "melatonin": "contraindication:supplement_melatonin_no_sedative_stack",
    "st_johns_wort": "contraindication:supplement_st_johns_wort_no_self_start_with_interacting_meds",
}

SUPPLEMENT_EVALS = {
    "vitamin_d": "eval:supplement_vitamin_d_ckd_boundary",
    "magnesium": "eval:supplement_magnesium_absorption_boundary",
    "omega3": "eval:supplement_omega3_bleeding_boundary",
    "caffeine": "eval:supplement_caffeine_sleep_boundary",
    "probiotic": "eval:supplement_probiotic_immunocompromised_boundary",
    "melatonin": "eval:supplement_melatonin_sedative_boundary",
    "st_johns_wort": "eval:supplement_st_johns_wort_interaction_boundary",
}


def _claim(doc_id: str) -> dict:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _twin(
    *,
    supplements: list[dict[str, Any]],
    medications: list[dict[str, Any]] | None = None,
    egfr: float | None = None,
    sleep_hours: float | None = None,
    conditions: list[str] | None = None,
):
    from app.twin.schema import (
        ChronicConditionState,
        HealthTwin,
        LabsContext,
        MedicationState,
        PhysiologicalState,
        SupplementState,
        TwinMeta,
    )

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.supplement = SupplementState(
        active_supplements=supplements,
        total_active_count=len(supplements),
    )
    twin.medication = MedicationState(
        active_meds=medications or [],
        has_any=bool(medications),
    )
    if egfr is not None:
        twin.labs = LabsContext(egfr=egfr)
    if sleep_hours is not None:
        twin.physiological = PhysiologicalState(sleep_duration_h_latest=sleep_hours)
    if conditions:
        twin.chronic = ChronicConditionState(active_conditions=conditions)
    return twin


def _claim_ids_for_twin(db, twin) -> set[str]:
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    payload = system_kb_twin_payload_from_health_twin(twin)
    result = lookup_for_twin(db, payload)
    return {claim.get("doc_id") for claim in result.get("claims") or []}


def test_supplement_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_safety_import")
    assert counts["skipped_documents"] == 0

    doc_ids = set(SUPPLEMENT_CLAIMS.values()) | set(SUPPLEMENT_CONTRAINDICATIONS.values()) | set(
        SUPPLEMENT_EVALS.values()
    )
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in SUPPLEMENT_CLAIMS.values():
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in SUPPLEMENT_CONTRAINDICATIONS.values():
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in SUPPLEMENT_EVALS.values():
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_vitamin_d_lookup_requires_kidney_risk_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_vitamin_d_lookup")

    risky = _twin(supplements=[{"name": "维生素D3"}], egfr=45)
    assert SUPPLEMENT_CLAIMS["vitamin_d"] in _claim_ids_for_twin(db, risky)

    low_risk = _twin(supplements=[{"name": "维生素D3"}], egfr=90)
    assert SUPPLEMENT_CLAIMS["vitamin_d"] not in _claim_ids_for_twin(db, low_risk)


def test_magnesium_lookup_requires_absorption_medication_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_magnesium_lookup")

    risky = _twin(
        supplements=[{"name": "甘氨酸镁"}],
        medications=[{"name": "左甲状腺素", "generic_name": "levothyroxine"}],
    )
    assert SUPPLEMENT_CLAIMS["magnesium"] in _claim_ids_for_twin(db, risky)

    no_medication = _twin(supplements=[{"name": "甘氨酸镁"}])
    assert SUPPLEMENT_CLAIMS["magnesium"] not in _claim_ids_for_twin(db, no_medication)


def test_omega3_lookup_requires_bleeding_medication_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_omega3_lookup")

    risky = _twin(
        supplements=[{"name": "Omega-3 鱼油"}],
        medications=[{"name": "华法林", "generic_name": "warfarin"}],
    )
    assert SUPPLEMENT_CLAIMS["omega3"] in _claim_ids_for_twin(db, risky)

    no_medication = _twin(supplements=[{"name": "Omega-3 鱼油"}])
    assert SUPPLEMENT_CLAIMS["omega3"] not in _claim_ids_for_twin(db, no_medication)


def test_caffeine_lookup_requires_poor_sleep_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_caffeine_lookup")

    risky = _twin(supplements=[{"name": "咖啡因胶囊"}], sleep_hours=5.2)
    assert SUPPLEMENT_CLAIMS["caffeine"] in _claim_ids_for_twin(db, risky)

    enough_sleep = _twin(supplements=[{"name": "咖啡因胶囊"}], sleep_hours=7.2)
    assert SUPPLEMENT_CLAIMS["caffeine"] not in _claim_ids_for_twin(db, enough_sleep)


def test_probiotic_lookup_requires_immunocompromised_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_probiotic_lookup")

    risky = _twin(
        supplements=[{"name": "益生菌"}],
        conditions=["化疗后免疫抑制"],
    )
    assert SUPPLEMENT_CLAIMS["probiotic"] in _claim_ids_for_twin(db, risky)

    no_condition = _twin(supplements=[{"name": "益生菌"}])
    assert SUPPLEMENT_CLAIMS["probiotic"] not in _claim_ids_for_twin(db, no_condition)


def test_melatonin_lookup_requires_sedative_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_melatonin_lookup")

    risky = _twin(
        supplements=[{"name": "褪黑素"}],
        medications=[{"name": "唑吡坦", "generic_name": "zolpidem"}],
    )
    assert SUPPLEMENT_CLAIMS["melatonin"] in _claim_ids_for_twin(db, risky)

    no_medication = _twin(supplements=[{"name": "褪黑素"}])
    assert SUPPLEMENT_CLAIMS["melatonin"] not in _claim_ids_for_twin(db, no_medication)


def test_st_johns_wort_lookup_requires_interacting_medication_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_st_johns_wort_lookup")

    risky = _twin(
        supplements=[{"name": "圣约翰草"}],
        medications=[{"name": "舍曲林", "generic_name": "sertraline"}],
    )
    assert SUPPLEMENT_CLAIMS["st_johns_wort"] in _claim_ids_for_twin(db, risky)

    supplement_only = _twin(supplements=[{"name": "圣约翰草"}])
    assert SUPPLEMENT_CLAIMS["st_johns_wort"] not in _claim_ids_for_twin(db, supplement_only)


def test_system_kb_eval_runner_covers_supplement_safety_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:supplement_safety_eval")

    report = run_system_kb_eval_cases(db, case_ids=set(SUPPLEMENT_EVALS.values()))

    assert report["total"] == 7
    assert report["failed"] == 0, report
    assert {case["case_id"] for case in report["cases"]} == set(SUPPLEMENT_EVALS.values())


def test_supplement_safety_claims_keep_actions_in_clinician_boundary():
    for doc_id in SUPPLEMENT_CLAIMS.values():
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("医生", "药师", "不替代", "边界")), doc_id
        for banned in [
            "自行停药",
            "自行换药",
            "自行调整",
            "直接停用",
            "推荐剂量",
            "每日服用",
            "每天服用",
            "治疗疾病",
            "确诊",
        ]:
            assert banned not in blob, f"{doc_id} 越界: {banned}"
