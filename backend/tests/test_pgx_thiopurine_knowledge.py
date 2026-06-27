"""TPMT/NUDT15 thiopurine reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

TPMT_CLAIM = "claim:c_tpmt_thiopurine_myelosuppression_boundary"
NUDT15_CLAIM = "claim:c_nudt15_thiopurine_myelosuppression_boundary"
THIOPURINE_CONTRAINDICATION = "contraindication:tpmt_nudt15_no_self_adjust_thiopurines"
THIOPURINE_EVAL = "eval:tpmt_nudt15_thiopurine_medication_boundary"


def _tpmt_thiopurine_twin():
    from app.twin.schema import GeneticContext, HealthTwin, MedicationState, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.genetic = GeneticContext(
        has_profile=True,
        drug_sensitivity=[
            {
                "gene_name": "TPMT",
                "genotype": "*3A/*3A",
                "result_label": "poor metabolizer",
                "risk_level": "high",
            }
        ],
    )
    twin.medication = MedicationState(
        has_any=True,
        active_meds=[
            {
                "name": "硫唑嘌呤",
                "generic_name": "azathioprine",
            }
        ],
    )
    return twin


def _nudt15_thiopurine_twin():
    from app.twin.schema import GeneticContext, HealthTwin, MedicationState, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.genetic = GeneticContext(
        has_profile=True,
        drug_sensitivity=[
            {
                "gene_name": "NUDT15",
                "genotype": "*3/*3",
                "result_label": "poor metabolizer",
                "risk_level": "high",
            }
        ],
    )
    twin.medication = MedicationState(
        has_any=True,
        active_meds=[
            {
                "name": "巯嘌呤",
                "generic_name": "mercaptopurine",
            }
        ],
    )
    return twin


def _claim(doc_id: str) -> dict:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def test_intersects_condition_requires_gene_and_medication_context(db):
    from app.services.system_knowledge_service import evaluate_condition, lookup_for_twin

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_intersects")

    assert evaluate_condition(
        "twin.medications intersects ['azathioprine', 'mercaptopurine']",
        {"medications": [{"name": "硫唑嘌呤", "generic_name": "azathioprine"}]},
    ) is True

    medication_only = {
        "genetics": {},
        "medications": [{"name": "硫唑嘌呤", "generic_name": "azathioprine"}],
    }
    result = lookup_for_twin(db, medication_only)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert TPMT_CLAIM not in claim_ids
    assert NUDT15_CLAIM not in claim_ids


def test_tpmt_twin_maps_to_kb_payload_and_lookup(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_lookup")

    payload = system_kb_twin_payload_from_health_twin(_tpmt_thiopurine_twin())
    assert payload["genetics"]["TPMT"] == "*3A/*3A"
    assert payload["genetics"]["TPMT_phenotype"] == "poor_metabolizer"
    assert payload["genetics"]["TPMT_activity"] == "absent"
    assert payload["medications"][0]["generic_name"] == "azathioprine"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert TPMT_CLAIM in claim_ids


def test_nudt15_twin_maps_to_kb_payload_and_lookup(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_nudt15_lookup")

    payload = system_kb_twin_payload_from_health_twin(_nudt15_thiopurine_twin())
    assert payload["genetics"]["NUDT15"] == "*3/*3"
    assert payload["genetics"]["NUDT15_phenotype"] == "poor_metabolizer"
    assert payload["genetics"]["NUDT15_function"] == "no_function"
    assert payload["medications"][0]["generic_name"] == "mercaptopurine"

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert NUDT15_CLAIM in claim_ids


def test_thiopurine_claim_attaches_to_safety_guardian_alert(db):
    from app.orchestrator.specialists import SafetyGuardianSpecialist
    from app.services.system_knowledge_service import (
        attach_system_knowledge_evidence,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_evidence")

    twin = _tpmt_thiopurine_twin()
    finding = SafetyGuardianSpecialist().run(twin, {})
    alert = next(item for item in finding.findings if item.get("rule_id") == "pgx.cpic.tpmt_硫唑嘌呤")

    payload = system_kb_twin_payload_from_health_twin(twin)
    stats = attach_system_knowledge_evidence(db, payload, [finding])

    assert stats["findings_updated"] >= 1
    assert TPMT_CLAIM in (finding.evidence_refs or [])
    assert TPMT_CLAIM in (alert.get("evidence_refs") or [])


def test_thiopurine_claim_contraindication_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_import")
    assert counts["skipped_documents"] == 0

    docs = db.query(KBDocument).filter(
        KBDocument.doc_id.in_({
            TPMT_CLAIM,
            NUDT15_CLAIM,
            THIOPURINE_CONTRAINDICATION,
            THIOPURINE_EVAL,
        })
    ).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == {
        TPMT_CLAIM,
        NUDT15_CLAIM,
        THIOPURINE_CONTRAINDICATION,
        THIOPURINE_EVAL,
    }
    assert by_id[THIOPURINE_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[THIOPURINE_EVAL].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed"


def test_system_kb_eval_runner_covers_thiopurine_pgx_case(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:pgx_eval")

    report = run_system_kb_eval_cases(db, case_ids={THIOPURINE_EVAL})

    assert report["total"] == 1
    assert report["failed"] == 0
    assert report["cases"][0]["case_id"] == THIOPURINE_EVAL


def test_thiopurine_claim_boundary_and_no_self_dosing():
    claim = _claim(TPMT_CLAIM)
    blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
    meta = claim.get("metadata") or {}
    assert meta.get("claim_boundary")
    assert "边界" in claim.get("body", "")
    assert any(token in blob for token in ("临床 PGx", "血常规", "不直接给出剂量"))
    for banned in [
        "自行停药",
        "自行启动",
        "自行调整",
        "直接减量",
        "直接停用",
        "推荐剂量",
        "确诊",
    ]:
        assert banned not in blob, f"{TPMT_CLAIM} 越界: {banned}"
