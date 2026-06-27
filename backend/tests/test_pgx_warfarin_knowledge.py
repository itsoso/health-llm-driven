"""Warfarin PGx reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

CYP2C9_WARFARIN_CLAIM = "claim:c_cyp2c9_warfarin_dose_boundary"
VKORC1_WARFARIN_CLAIM = "claim:c_vkorc1_warfarin_inr_boundary"
WARFARIN_CONTRAINDICATION = "contraindication:cyp2c9_vkorc1_no_self_adjust_warfarin"
WARFARIN_EVAL = "eval:cyp2c9_vkorc1_warfarin_inr_boundary"


def _claim(doc_id: str) -> dict:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _warfarin_twin():
    from app.twin.schema import GeneticContext, HealthTwin, MedicationState, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.genetic = GeneticContext(
        has_profile=True,
        drug_sensitivity=[
            {
                "gene_name": "CYP2C9",
                "genotype": "*1/*3",
                "result_label": "intermediate metabolizer / reduced warfarin clearance",
                "risk_level": "medium",
            },
            {
                "gene_name": "VKORC1",
                "genotype": "A/G",
                "result_label": "warfarin sensitivity allele",
                "risk_level": "medium",
            },
        ],
    )
    twin.medication = MedicationState(
        has_any=True,
        active_meds=[{"name": "华法林", "generic_name": "warfarin"}],
    )
    return twin


def test_warfarin_pgx_claims_contraindication_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_warfarin_import")
    assert counts["skipped_documents"] == 0

    doc_ids = {
        CYP2C9_WARFARIN_CLAIM,
        VKORC1_WARFARIN_CLAIM,
        WARFARIN_CONTRAINDICATION,
        WARFARIN_EVAL,
    }
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    assert by_id[CYP2C9_WARFARIN_CLAIM].doc_type == "claim"
    assert by_id[VKORC1_WARFARIN_CLAIM].doc_type == "claim"
    assert by_id[WARFARIN_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[WARFARIN_EVAL].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_warfarin_pgx_health_twin_maps_to_kb_lookup_context(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_warfarin_lookup")

    payload = system_kb_twin_payload_from_health_twin(_warfarin_twin())
    assert payload["genetics"]["CYP2C9"] == "*1/*3"
    assert payload["genetics"]["CYP2C9_phenotype"] == "intermediate"
    assert payload["genetics"]["VKORC1"] == "A/G"
    assert payload["genetics"]["VKORC1_1639G_A"] == "A/G"
    assert payload["genetics"]["VKORC1_rs9923231"] == "A/G"
    assert payload["medications"][0]["generic_name"] == "warfarin"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert CYP2C9_WARFARIN_CLAIM in claim_ids
    assert VKORC1_WARFARIN_CLAIM in claim_ids

    no_medication = dict(payload)
    no_medication["medications"] = []
    no_medication_result = lookup_for_twin(db, no_medication)
    no_medication_claim_ids = {
        claim.get("doc_id") for claim in no_medication_result.get("claims") or []
    }
    assert CYP2C9_WARFARIN_CLAIM not in no_medication_claim_ids
    assert VKORC1_WARFARIN_CLAIM not in no_medication_claim_ids


def test_system_kb_eval_runner_covers_warfarin_pgx_case(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_warfarin_eval")

    report = run_system_kb_eval_cases(db, case_ids={WARFARIN_EVAL})

    assert report["total"] == 1
    assert report["failed"] == 0
    assert report["cases"][0]["case_id"] == WARFARIN_EVAL


def test_warfarin_pgx_claims_keep_dosing_in_clinician_boundary():
    for doc_id in (CYP2C9_WARFARIN_CLAIM, VKORC1_WARFARIN_CLAIM):
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert "INR" in blob, doc_id
        assert any(token in blob for token in ("医生", "抗凝门诊", "不替代")), doc_id
        for banned in [
            "自行换药",
            "自行停药",
            "自行调整",
            "直接换药",
            "直接停用",
            "推荐剂量",
            "每日服用",
            "每天服用",
            "确诊",
        ]:
            assert banned not in blob, f"{doc_id} 越界: {banned}"
