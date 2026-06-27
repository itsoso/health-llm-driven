"""Gastro medication-safety reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

GASTRO_MED_CLAIMS = {
    "nsaid_antithrombotic": "claim:c_gastro_nsaid_antithrombotic_bleeding_boundary",
    "long_term_ppi": "claim:c_gastro_long_term_acid_suppression_review_loop",
}

GASTRO_MED_CONTRAINDICATIONS = {
    "nsaid_antithrombotic": "contraindication:gastro_nsaid_antithrombotic_no_self_manage_bleeding",
    "long_term_ppi": "contraindication:gastro_long_term_acid_suppression_no_self_deprescribing",
}

GASTRO_MED_EVALS = {
    "nsaid_antithrombotic": "eval:gastro_nsaid_antithrombotic_bleeding_boundary",
    "long_term_ppi": "eval:gastro_long_term_acid_suppression_review_loop",
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
    medications: list[dict[str, Any]],
    conditions: list[str] | None = None,
):
    from app.twin.schema import ChronicConditionState, HealthTwin, MedicationState, TwinMeta

    twin = HealthTwin(
        meta=TwinMeta(user_id=1, generated_at=datetime(2026, 6, 27, tzinfo=UTC))
    )
    twin.medication = MedicationState(
        active_meds=medications,
        has_any=bool(medications),
    )
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


def test_gastro_medication_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:gastro_med_safety_import")
    assert counts["skipped_documents"] == 0

    doc_ids = (
        set(GASTRO_MED_CLAIMS.values())
        | set(GASTRO_MED_CONTRAINDICATIONS.values())
        | set(GASTRO_MED_EVALS.values())
    )
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in GASTRO_MED_CLAIMS.values():
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in GASTRO_MED_CONTRAINDICATIONS.values():
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in GASTRO_MED_EVALS.values():
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_nsaid_antithrombotic_lookup_requires_gastric_condition_and_second_medication(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:gastro_nsaid_bleeding_lookup")

    risky = _twin(
        conditions=["消化性溃疡"],
        medications=[
            {"name": "布洛芬", "generic_name": "ibuprofen"},
            {"name": "华法林", "generic_name": "warfarin"},
        ],
    )
    assert GASTRO_MED_CLAIMS["nsaid_antithrombotic"] in _claim_ids_for_twin(db, risky)

    no_gastric_condition = _twin(
        conditions=["腰痛"],
        medications=[
            {"name": "布洛芬", "generic_name": "ibuprofen"},
            {"name": "华法林", "generic_name": "warfarin"},
        ],
    )
    assert (
        GASTRO_MED_CLAIMS["nsaid_antithrombotic"]
        not in _claim_ids_for_twin(db, no_gastric_condition)
    )

    no_antithrombotic = _twin(
        conditions=["消化性溃疡"],
        medications=[{"name": "布洛芬", "generic_name": "ibuprofen"}],
    )
    assert (
        GASTRO_MED_CLAIMS["nsaid_antithrombotic"]
        not in _claim_ids_for_twin(db, no_antithrombotic)
    )


def test_long_term_acid_suppression_lookup_requires_duration_context(db):
    from app.services.system_knowledge_service import system_kb_twin_payload_from_health_twin

    import_system_kb_artifacts(db, SEED_DIR, actor="test:gastro_long_term_ppi_lookup")

    long_term = _twin(
        conditions=["胃食管反流"],
        medications=[{"name": "奥美拉唑", "generic_name": "omeprazole", "start_date": "2026-04-01"}],
    )
    payload = system_kb_twin_payload_from_health_twin(long_term)
    assert payload["medication_context"]["acid_suppression_weeks_max"] >= 8
    assert GASTRO_MED_CLAIMS["long_term_ppi"] in _claim_ids_for_twin(db, long_term)

    class_only_long_term = _twin(
        conditions=["胃食管反流"],
        medications=[{"class": "PPI", "start_date": "2026-04-01"}],
    )
    class_only_payload = system_kb_twin_payload_from_health_twin(class_only_long_term)
    assert class_only_payload["medication_context"]["acid_suppression_active"] is True
    assert class_only_payload["medication_context"]["acid_suppression_weeks_max"] >= 8
    assert GASTRO_MED_CLAIMS["long_term_ppi"] in _claim_ids_for_twin(db, class_only_long_term)

    short_term = _twin(
        conditions=["胃食管反流"],
        medications=[{"name": "奥美拉唑", "generic_name": "omeprazole", "start_date": "2026-06-10"}],
    )
    assert GASTRO_MED_CLAIMS["long_term_ppi"] not in _claim_ids_for_twin(db, short_term)

    no_start_date = _twin(
        conditions=["胃食管反流"],
        medications=[{"name": "奥美拉唑", "generic_name": "omeprazole"}],
    )
    assert GASTRO_MED_CLAIMS["long_term_ppi"] not in _claim_ids_for_twin(db, no_start_date)


def test_system_kb_eval_runner_covers_gastro_medication_safety_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:gastro_med_safety_eval")

    report = run_system_kb_eval_cases(db, case_ids=set(GASTRO_MED_EVALS.values()))

    assert report["total"] == 2
    assert report["failed"] == 0, report
    assert {case["case_id"] for case in report["cases"]} == set(GASTRO_MED_EVALS.values())


def test_gastro_medication_safety_claims_keep_actions_in_clinician_boundary():
    for doc_id in GASTRO_MED_CLAIMS.values():
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("医生", "药师", "消化科", "不替代", "边界")), doc_id
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
            "四联",
            "阿莫西林",
            "克拉霉素",
            "甲硝唑",
        ]:
            assert banned not in blob, f"{doc_id} 越界: {banned}"
