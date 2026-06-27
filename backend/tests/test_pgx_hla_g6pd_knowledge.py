"""HLA and G6PD PGx reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

HLA_A3101_CLAIM = "claim:c_hla_a3101_carbamazepine_boundary"
HLA_B5801_CLAIM = "claim:c_hla_b5801_allopurinol_boundary"
G6PD_CLAIM = "claim:c_g6pd_oxidant_drug_hemolysis_boundary"

HLA_A3101_CONTRAINDICATION = "contraindication:hla_a3101_no_self_switch_carbamazepine"
HLA_B5801_CONTRAINDICATION = "contraindication:hla_b5801_no_self_switch_allopurinol"
G6PD_CONTRAINDICATION = "contraindication:g6pd_no_self_manage_oxidant_drugs"

HLA_A3101_EVAL = "eval:hla_a3101_carbamazepine_boundary"
HLA_B5801_EVAL = "eval:hla_b5801_allopurinol_boundary"
G6PD_EVAL = "eval:g6pd_oxidant_drug_boundary"


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


def _hla_a3101_twin():
    return _pgx_twin(
        "HLA-A",
        "*31:01 positive",
        "HLA-A*31:01 阳性",
        {"name": "卡马西平", "generic_name": "carbamazepine"},
    )


def _hla_b5801_twin():
    return _pgx_twin(
        "HLA-B",
        "*58:01 positive",
        "HLA-B*58:01 阳性",
        {"name": "别嘌醇", "generic_name": "allopurinol"},
    )


def _g6pd_twin():
    return _pgx_twin(
        "G6PD",
        "deficient",
        "G6PD deficient / low activity",
        {"name": "氨苯砜", "generic_name": "dapsone"},
    )


def test_hla_g6pd_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_hla_g6pd_import")
    assert counts["skipped_documents"] == 0

    doc_ids = {
        HLA_A3101_CLAIM,
        HLA_B5801_CLAIM,
        G6PD_CLAIM,
        HLA_A3101_CONTRAINDICATION,
        HLA_B5801_CONTRAINDICATION,
        G6PD_CONTRAINDICATION,
        HLA_A3101_EVAL,
        HLA_B5801_EVAL,
        G6PD_EVAL,
    }
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in (HLA_A3101_CLAIM, HLA_B5801_CLAIM, G6PD_CLAIM):
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in (HLA_A3101_CONTRAINDICATION, HLA_B5801_CONTRAINDICATION, G6PD_CONTRAINDICATION):
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in (HLA_A3101_EVAL, HLA_B5801_EVAL, G6PD_EVAL):
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_hla_a3101_health_twin_requires_carbamazepine_context(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_hla_a3101_lookup")

    payload = system_kb_twin_payload_from_health_twin(_hla_a3101_twin())
    assert payload["genetics"]["HLA_A_31_01"] == "positive"
    assert payload["genetics"]["HLA-A*31:01"] == "positive"
    assert payload["genetics"]["HLA_A_3101"] == "positive"
    assert payload["medications"][0]["generic_name"] == "carbamazepine"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert HLA_A3101_CLAIM in claim_ids

    no_medication = dict(payload)
    no_medication["medications"] = []
    no_medication_result = lookup_for_twin(db, no_medication)
    no_medication_claim_ids = {
        claim.get("doc_id") for claim in no_medication_result.get("claims") or []
    }
    assert HLA_A3101_CLAIM not in no_medication_claim_ids


def test_hla_b5801_health_twin_requires_allopurinol_context(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_hla_b5801_lookup")

    payload = system_kb_twin_payload_from_health_twin(_hla_b5801_twin())
    assert payload["genetics"]["HLA_B_58_01"] == "positive"
    assert payload["genetics"]["HLA-B*58:01"] == "positive"
    assert payload["medications"][0]["generic_name"] == "allopurinol"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert HLA_B5801_CLAIM in claim_ids

    no_medication = dict(payload)
    no_medication["medications"] = []
    no_medication_result = lookup_for_twin(db, no_medication)
    no_medication_claim_ids = {
        claim.get("doc_id") for claim in no_medication_result.get("claims") or []
    }
    assert HLA_B5801_CLAIM not in no_medication_claim_ids


def test_g6pd_health_twin_requires_oxidant_drug_context(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_g6pd_lookup")

    payload = system_kb_twin_payload_from_health_twin(_g6pd_twin())
    assert payload["genetics"]["G6PD"] == "deficient"
    assert payload["genetics"]["G6PD_phenotype"] == "deficient"
    assert payload["medications"][0]["generic_name"] == "dapsone"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert G6PD_CLAIM in claim_ids

    no_medication = dict(payload)
    no_medication["medications"] = []
    no_medication_result = lookup_for_twin(db, no_medication)
    no_medication_claim_ids = {
        claim.get("doc_id") for claim in no_medication_result.get("claims") or []
    }
    assert G6PD_CLAIM not in no_medication_claim_ids


def test_system_kb_eval_runner_covers_hla_g6pd_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_hla_g6pd_eval")

    report = run_system_kb_eval_cases(
        db,
        case_ids={HLA_A3101_EVAL, HLA_B5801_EVAL, G6PD_EVAL},
    )

    assert report["total"] == 3
    assert report["failed"] == 0
    assert {case["case_id"] for case in report["cases"]} == {
        HLA_A3101_EVAL,
        HLA_B5801_EVAL,
        G6PD_EVAL,
    }


def test_hla_g6pd_claims_keep_medication_changes_in_clinician_boundary():
    for doc_id in (HLA_A3101_CLAIM, HLA_B5801_CLAIM, G6PD_CLAIM):
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("医生", "处方", "不替代", "临床")), doc_id
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
