"""Genetic clinical-confirmation boundary reviewed-KB integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

GENETIC_CONFIRMATION_CLAIMS = {
    "brca1": "claim:c_brca1_dtc_confirmation_boundary",
    "brca2": "claim:c_brca2_dtc_confirmation_boundary",
}

GENETIC_CONFIRMATION_CONTRAINDICATIONS = {
    "brca1": "contraindication:brca1_dtc_no_diagnosis_or_surgery_decision",
    "brca2": "contraindication:brca2_dtc_no_diagnosis_or_surgery_decision",
}

GENETIC_CONFIRMATION_EVALS = {
    "brca1": "eval:brca1_dtc_confirmation_boundary",
    "brca2": "eval:brca2_dtc_confirmation_boundary",
}


def _claim(doc_id: str) -> dict[str, Any]:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _claim_ids_for_payload(db, payload: dict[str, Any]) -> set[str]:
    from app.services.system_knowledge_service import lookup_for_twin

    result = lookup_for_twin(db, payload)
    return {claim.get("doc_id") for claim in result.get("claims") or []}


def _condition_claim_ids_for_payload(db, payload: dict[str, Any]) -> set[str]:
    from app.services.system_knowledge_service import lookup_for_twin

    result = lookup_for_twin(db, payload)
    return {
        claim.get("doc_id")
        for claim in result.get("claims") or []
        if claim.get("match_type") == "condition"
    }


def test_genetic_confirmation_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:genetic_confirmation_import")
    assert counts["skipped_documents"] == 0

    doc_ids = (
        set(GENETIC_CONFIRMATION_CLAIMS.values())
        | set(GENETIC_CONFIRMATION_CONTRAINDICATIONS.values())
        | set(GENETIC_CONFIRMATION_EVALS.values())
    )
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in GENETIC_CONFIRMATION_CLAIMS.values():
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in GENETIC_CONFIRMATION_CONTRAINDICATIONS.values():
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in GENETIC_CONFIRMATION_EVALS.values():
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_brca_lookup_requires_gene_result_and_pathogenic_class(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:brca_confirmation_lookup")

    brca1_payload = {"genetics": {"BRCA1": "rs80357906", "BRCA1_variant_class": "pathogenic"}}
    assert GENETIC_CONFIRMATION_CLAIMS["brca1"] in _condition_claim_ids_for_payload(
        db, brca1_payload
    )

    brca2_payload = {
        "genetics": {"BRCA2": "rs80359550", "BRCA2_variant_class": "likely_pathogenic"}
    }
    assert GENETIC_CONFIRMATION_CLAIMS["brca2"] in _condition_claim_ids_for_payload(
        db, brca2_payload
    )

    vus_payload = {"genetics": {"BRCA1": "rs80357906", "BRCA1_variant_class": "vus"}}
    assert GENETIC_CONFIRMATION_CLAIMS["brca1"] not in _condition_claim_ids_for_payload(
        db, vus_payload
    )


def test_system_kb_eval_runner_covers_genetic_confirmation_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:genetic_confirmation_eval")

    report = run_system_kb_eval_cases(
        db,
        case_ids=set(GENETIC_CONFIRMATION_EVALS.values()),
    )

    assert report["total"] == 2
    assert report["failed"] == 0, report
    assert {case["case_id"] for case in report["cases"]} == set(
        GENETIC_CONFIRMATION_EVALS.values()
    )


def test_genetic_confirmation_claims_keep_actions_inside_confirmation_boundary():
    for doc_id in GENETIC_CONFIRMATION_CLAIMS.values():
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("遗传咨询", "临床级检测", "确认", "边界")), doc_id
        for banned in [
            "立即手术",
            "必须切除",
            "确诊为癌症",
            "诊断为癌症",
        ]:
            assert banned not in blob, f"{doc_id} 越界: {banned}"
