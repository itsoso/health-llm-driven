"""Sleep / nocturnal SpO2 reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

SLEEP_SPO2_CLAIM = "claim:c_nocturnal_spo2_osa_testing_boundary"
SLEEP_SPO2_CONTRAINDICATION = "contraindication:sleep_spo2_do_not_push_harder"
SLEEP_SPO2_EVAL = "eval:sleep_spo2_exercise_escalates_to_sleep_assessment"


def _sleep_spo2_twin():
    from app.twin.schema import HealthTwin, PhysiologicalState, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    twin.physiological = PhysiologicalState(
        spo2_avg=92.0,
        spo2_min_overnight=82,
        spo2_odi=8.0,
        spo2_below_90_pct=2.4,
    )
    return twin


def _sleep_spo2_claim() -> dict:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == SLEEP_SPO2_CLAIM:
            return row
    raise AssertionError(f"missing seed claim: {SLEEP_SPO2_CLAIM}")


def test_sleep_spo2_claim_contraindication_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_spo2")
    assert counts["skipped_documents"] == 0

    docs = db.query(KBDocument).filter(
        KBDocument.doc_id.in_({
            SLEEP_SPO2_CLAIM,
            SLEEP_SPO2_CONTRAINDICATION,
            SLEEP_SPO2_EVAL,
        })
    ).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == {SLEEP_SPO2_CLAIM, SLEEP_SPO2_CONTRAINDICATION, SLEEP_SPO2_EVAL}
    assert by_id[SLEEP_SPO2_CLAIM].doc_type == "claim"
    assert by_id[SLEEP_SPO2_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[SLEEP_SPO2_EVAL].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed"


def test_sleep_spo2_health_twin_maps_to_kb_payload_and_lookup(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_spo2_lookup")

    payload = system_kb_twin_payload_from_health_twin(_sleep_spo2_twin())
    assert payload["wearable"]["spo2_min_overnight"] == 82
    assert payload["wearable"]["spo2_odi"] == 8.0
    assert payload["wearable"]["spo2_below_90_pct"] == 2.4

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert SLEEP_SPO2_CLAIM in claim_ids


def test_sleep_spo2_claim_attaches_to_safety_guardian_alert(db):
    from app.orchestrator.specialists import SafetyGuardianSpecialist
    from app.services.system_knowledge_service import (
        attach_system_knowledge_evidence,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_spo2_evidence")

    twin = _sleep_spo2_twin()
    finding = SafetyGuardianSpecialist().run(twin, {})
    assert any(
        item.get("rule_id") == "vitals.spo2_min_nocturnal_severe"
        for item in finding.findings
    )

    payload = system_kb_twin_payload_from_health_twin(twin)
    stats = attach_system_knowledge_evidence(db, payload, [finding])

    assert stats["findings_updated"] >= 1
    assert SLEEP_SPO2_CLAIM in (finding.evidence_refs or [])


def test_system_kb_eval_runner_covers_sleep_spo2_case(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:sleep_spo2_eval")

    report = run_system_kb_eval_cases(db, case_ids={SLEEP_SPO2_EVAL})

    assert report["total"] == 1
    assert report["failed"] == 0
    assert report["cases"][0]["case_id"] == SLEEP_SPO2_EVAL


def test_sleep_spo2_claim_boundary_and_no_prescription():
    claim = _sleep_spo2_claim()
    blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
    meta = claim.get("metadata") or {}
    assert meta.get("claim_boundary")
    assert "边界" in claim.get("body", "")
    assert any(token in blob for token in ("睡眠中心", "医生", "就诊", "评估"))
    for banned in [
        "确诊",
        "诊断为",
        "你患有",
        "应该加大训练",
        "建议加大训练",
        "需要加大训练",
        "运动越多越好",
        "自行服用镇静药",
        "自行使用CPAP",
    ]:
        assert banned not in blob, f"{SLEEP_SPO2_CLAIM} 越界: {banned}"
