"""High-risk PGx reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

DPYD_CLAIM = "claim:c_dpyd_fluoropyrimidine_toxicity_boundary"
SLCO1B1_CLAIM = "claim:c_slco1b1_statin_myopathy_boundary"
HLA_B1502_CLAIM = "claim:c_hla_b1502_carbamazepine_oxcarbazepine_boundary"

DPYD_CONTRAINDICATION = "contraindication:dpyd_no_self_adjust_fluoropyrimidines"
SLCO1B1_CONTRAINDICATION = "contraindication:slco1b1_no_self_adjust_statin"
HLA_B1502_CONTRAINDICATION = "contraindication:hla_b1502_no_self_switch_carbamazepine"

DPYD_EVAL = "eval:dpyd_fluoropyrimidine_toxicity_boundary"
SLCO1B1_EVAL = "eval:slco1b1_statin_myopathy_boundary"
HLA_B1502_EVAL = "eval:hla_b1502_carbamazepine_boundary"


def _claim(doc_id: str) -> dict:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _pgx_twin(gene: str, genotype: str, result_label: str, drug: dict, risk: str = "high"):
    from app.twin.schema import GeneticContext, HealthTwin, MedicationState, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.genetic = GeneticContext(
        has_profile=True,
        drug_sensitivity=[
            {
                "gene_name": gene,
                "genotype": genotype,
                "result_label": result_label,
                "risk_level": risk,
            }
        ],
    )
    twin.medication = MedicationState(has_any=True, active_meds=[drug])
    return twin


def _dpyd_twin():
    return _pgx_twin(
        "DPYD",
        "*1/*2A",
        "intermediate metabolizer / reduced DPD activity",
        {"name": "卡培他滨", "generic_name": "capecitabine"},
        risk="medium",
    )


def _slco1b1_twin():
    return _pgx_twin(
        "SLCO1B1",
        "CC",
        "poor function",
        {"name": "辛伐他汀", "generic_name": "simvastatin"},
    )


def _hla_b1502_twin():
    return _pgx_twin(
        "HLA-B",
        "*15:02 positive",
        "HLA-B*15:02 阳性",
        {"name": "卡马西平", "generic_name": "carbamazepine"},
    )


def test_high_risk_pgx_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_high_risk_import")
    assert counts["skipped_documents"] == 0

    doc_ids = {
        DPYD_CLAIM,
        SLCO1B1_CLAIM,
        HLA_B1502_CLAIM,
        DPYD_CONTRAINDICATION,
        SLCO1B1_CONTRAINDICATION,
        HLA_B1502_CONTRAINDICATION,
        DPYD_EVAL,
        SLCO1B1_EVAL,
        HLA_B1502_EVAL,
    }
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in (DPYD_CLAIM, SLCO1B1_CLAIM, HLA_B1502_CLAIM):
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in (DPYD_CONTRAINDICATION, SLCO1B1_CONTRAINDICATION, HLA_B1502_CONTRAINDICATION):
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in (DPYD_EVAL, SLCO1B1_EVAL, HLA_B1502_EVAL):
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_dpyd_health_twin_maps_to_kb_lookup_context(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_dpyd_lookup")

    payload = system_kb_twin_payload_from_health_twin(_dpyd_twin())
    assert payload["genetics"]["DPYD"] == "*1/*2A"
    assert payload["genetics"]["DPYD_phenotype"] == "intermediate_metabolizer"
    assert payload["genetics"]["DPD_activity_score"] == "1"
    assert payload["medications"][0]["generic_name"] == "capecitabine"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert DPYD_CLAIM in claim_ids


def test_slco1b1_health_twin_maps_to_kb_lookup_context(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_slco_lookup")

    payload = system_kb_twin_payload_from_health_twin(_slco1b1_twin())
    assert payload["genetics"]["SLCO1B1"] == "CC"
    assert payload["genetics"]["SLCO1B1_rs4149056"] == "CC"
    assert payload["medications"][0]["generic_name"] == "simvastatin"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert SLCO1B1_CLAIM in claim_ids


def test_hla_b1502_health_twin_maps_to_kb_lookup_context(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_hla_lookup")

    payload = system_kb_twin_payload_from_health_twin(_hla_b1502_twin())
    assert payload["genetics"]["HLA_B_15_02"] == "positive"
    assert payload["genetics"]["HLA-B*15:02"] == "positive"
    assert payload["medications"][0]["generic_name"] == "carbamazepine"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert HLA_B1502_CLAIM in claim_ids

    no_medication = dict(payload)
    no_medication["medications"] = []
    no_medication_result = lookup_for_twin(db, no_medication)
    no_medication_claim_ids = {
        claim.get("doc_id") for claim in no_medication_result.get("claims") or []
    }
    assert HLA_B1502_CLAIM not in no_medication_claim_ids


def test_system_kb_eval_runner_covers_high_risk_pgx_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_high_risk_eval")

    report = run_system_kb_eval_cases(
        db,
        case_ids={DPYD_EVAL, SLCO1B1_EVAL, HLA_B1502_EVAL},
    )

    assert report["total"] == 3
    assert report["failed"] == 0
    assert {case["case_id"] for case in report["cases"]} == {
        DPYD_EVAL,
        SLCO1B1_EVAL,
        HLA_B1502_EVAL,
    }


def test_high_risk_pgx_claims_keep_medication_changes_in_clinician_boundary():
    for doc_id in (DPYD_CLAIM, SLCO1B1_CLAIM, HLA_B1502_CLAIM):
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("医生", "处方", "肿瘤科", "不替代")), doc_id
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
