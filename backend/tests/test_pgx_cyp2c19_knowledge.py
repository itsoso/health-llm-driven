"""CYP2C19 CPIC reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

CYP2C19_CLOPIDOGREL_CLAIM = "claim:c_cyp2c19_clopidogrel_boundary"
CYP2C19_PPI_CLAIM = "claim:c_cyp2c19_ppi_substitution"
CYP2C19_CONTRAINDICATION = "contraindication:cyp2c19_no_self_switch_antiplatelet_or_ppi"
CYP2C19_CLOPIDOGREL_EVAL = "eval:cyp2c19_clopidogrel_cpic_boundary"
CYP2C19_PPI_EVAL = "eval:cyp2c19_ppi_cpic_boundary"


def _claim(doc_id: str) -> dict:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _cyp2c19_clopidogrel_twin():
    from app.twin.schema import GeneticContext, HealthTwin, MedicationState, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.genetic = GeneticContext(
        has_profile=True,
        drug_sensitivity=[
            {
                "gene_name": "CYP2C19",
                "genotype": "*2/*2",
                "result_label": "poor metabolizer",
                "risk_level": "high",
            }
        ],
    )
    twin.medication = MedicationState(
        has_any=True,
        active_meds=[
            {
                "name": "波立维",
                "generic_name": "clopidogrel",
            }
        ],
    )
    return twin


def _cyp2c19_ppi_twin():
    from app.twin.schema import GeneticContext, HealthTwin, MedicationState, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.genetic = GeneticContext(
        has_profile=True,
        drug_sensitivity=[
            {
                "gene_name": "CYP2C19",
                "genotype": "*2/*3",
                "result_label": "慢代谢",
                "risk_level": "high",
            }
        ],
    )
    twin.medication = MedicationState(
        has_any=True,
        active_meds=[
            {
                "name": "奥美拉唑",
                "generic_name": "omeprazole",
            }
        ],
    )
    return twin


def test_cyp2c19_claims_contraindication_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:cyp2c19_import")
    assert counts["skipped_documents"] == 0

    doc_ids = {
        CYP2C19_CLOPIDOGREL_CLAIM,
        CYP2C19_PPI_CLAIM,
        CYP2C19_CONTRAINDICATION,
        CYP2C19_CLOPIDOGREL_EVAL,
        CYP2C19_PPI_EVAL,
    }
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    assert by_id[CYP2C19_CLOPIDOGREL_CLAIM].doc_type == "claim"
    assert by_id[CYP2C19_PPI_CLAIM].doc_type == "claim"
    assert by_id[CYP2C19_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[CYP2C19_CLOPIDOGREL_EVAL].doc_type == "eval_case"
    assert by_id[CYP2C19_PPI_EVAL].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_cyp2c19_health_twin_maps_to_lookup_context(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:cyp2c19_lookup")

    clopidogrel_payload = system_kb_twin_payload_from_health_twin(_cyp2c19_clopidogrel_twin())
    assert clopidogrel_payload["genetics"]["CYP2C19"] == "*2/*2"
    assert clopidogrel_payload["genetics"]["CYP2C19_phenotype"] == "poor"
    assert clopidogrel_payload["medications"][0]["generic_name"] == "clopidogrel"

    clopidogrel_result = lookup_for_twin(db, clopidogrel_payload)
    clopidogrel_claim_ids = {
        claim.get("doc_id") for claim in clopidogrel_result.get("claims") or []
    }
    assert CYP2C19_CLOPIDOGREL_CLAIM in clopidogrel_claim_ids
    assert CYP2C19_PPI_CLAIM not in clopidogrel_claim_ids

    ppi_payload = system_kb_twin_payload_from_health_twin(_cyp2c19_ppi_twin())
    assert ppi_payload["genetics"]["CYP2C19_phenotype"] == "poor"
    assert ppi_payload["medications"][0]["generic_name"] == "omeprazole"

    ppi_result = lookup_for_twin(db, ppi_payload)
    ppi_claim_ids = {claim.get("doc_id") for claim in ppi_result.get("claims") or []}
    assert CYP2C19_PPI_CLAIM in ppi_claim_ids


def test_cyp2c19_lookup_requires_medication_context(db):
    from app.services.system_knowledge_service import lookup_for_twin

    import_system_kb_artifacts(db, SEED_DIR, actor="test:cyp2c19_no_med")

    result = lookup_for_twin(
        db,
        {
            "genetics": {"CYP2C19_phenotype": "poor"},
            "medications": [],
        },
    )
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert CYP2C19_CLOPIDOGREL_CLAIM not in claim_ids
    assert CYP2C19_PPI_CLAIM not in claim_ids


def test_system_kb_eval_runner_covers_cyp2c19_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:cyp2c19_eval")

    report = run_system_kb_eval_cases(
        db,
        case_ids={CYP2C19_CLOPIDOGREL_EVAL, CYP2C19_PPI_EVAL},
    )

    assert report["total"] == 2
    assert report["failed"] == 0
    assert {case["case_id"] for case in report["cases"]} == {
        CYP2C19_CLOPIDOGREL_EVAL,
        CYP2C19_PPI_EVAL,
    }


def test_cyp2c19_claim_boundaries_do_not_self_switch_or_dose():
    for doc_id in (CYP2C19_CLOPIDOGREL_CLAIM, CYP2C19_PPI_CLAIM):
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary")
        assert any(token in blob for token in ("医生", "专业", "处方", "剂量调整")), doc_id
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
