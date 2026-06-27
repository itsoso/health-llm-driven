"""Acute illness / exercise reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

ACUTE_EXERCISE_CLAIM = "claim:c_acute_illness_exercise_rest_boundary"
ACUTE_EXERCISE_CONTRAINDICATION = "contraindication:acute_illness_no_training_escalation"
ACUTE_EXERCISE_EVAL = "eval:acute_illness_exercise_rest_boundary"


def _acute_fever_twin():
    from app.twin.schema import AcuteHealthState, HealthTwin, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.acute = AcuteHealthState(
        has_active_illness=True,
        illness_names=["感冒"],
        illness_severity_max=5,
        recent_symptoms=["发热 38.2 度", "咽痛", "咳嗽"],
        symptom_texts_all=["发热 38.2 度", "咽痛", "咳嗽"],
        suspected_cold=True,
        fever_reported=True,
        should_rest_from_training=True,
        training_guardrail="发热/疑似感染期暂停训练；退热且症状明显缓解后再从低强度恢复。",
    )
    return twin


def _acute_exercise_claim() -> dict:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == ACUTE_EXERCISE_CLAIM:
            return row
    raise AssertionError(f"missing seed claim: {ACUTE_EXERCISE_CLAIM}")


def test_acute_exercise_claim_contraindication_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:acute_exercise")
    assert counts["skipped_documents"] == 0

    docs = db.query(KBDocument).filter(
        KBDocument.doc_id.in_({
            ACUTE_EXERCISE_CLAIM,
            ACUTE_EXERCISE_CONTRAINDICATION,
            ACUTE_EXERCISE_EVAL,
        })
    ).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == {
        ACUTE_EXERCISE_CLAIM,
        ACUTE_EXERCISE_CONTRAINDICATION,
        ACUTE_EXERCISE_EVAL,
    }
    assert by_id[ACUTE_EXERCISE_CLAIM].doc_type == "claim"
    assert by_id[ACUTE_EXERCISE_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[ACUTE_EXERCISE_EVAL].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed"


def test_acute_exercise_twin_maps_to_kb_payload_and_lookup(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:acute_exercise_lookup")

    payload = system_kb_twin_payload_from_health_twin(_acute_fever_twin())
    assert payload["acute"]["has_active_illness"] is True
    assert payload["acute"]["fever_reported"] is True
    assert payload["acute"]["should_rest_from_training"] is True
    assert "发热 38.2 度" in payload["acute"]["symptoms"]
    assert "感冒" in payload["acute"]["illness_names"]

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert ACUTE_EXERCISE_CLAIM in claim_ids


def test_acute_exercise_claim_attaches_to_movement_coach_rest_advice(db):
    from app.agents.movement_coach import MovementCoachSpecialist
    from app.services.system_knowledge_service import (
        attach_system_knowledge_evidence,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:acute_exercise_evidence")

    twin = _acute_fever_twin()
    finding = MovementCoachSpecialist().run(twin, {"readiness_zone": "good"})
    prescription = next(item for item in finding.findings if item.get("type") == "today_prescription")
    assert prescription["intensity"] == "rest"
    assert prescription["reason"] == "acute_illness"

    payload = system_kb_twin_payload_from_health_twin(twin)
    stats = attach_system_knowledge_evidence(db, payload, [finding])

    assert stats["findings_updated"] >= 1
    assert ACUTE_EXERCISE_CLAIM in (finding.evidence_refs or [])
    assert ACUTE_EXERCISE_CLAIM in (prescription.get("evidence_refs") or [])


def test_system_kb_eval_runner_covers_acute_exercise_case(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:acute_exercise_eval")

    report = run_system_kb_eval_cases(db, case_ids={ACUTE_EXERCISE_EVAL})

    assert report["total"] == 1
    assert report["failed"] == 0
    assert report["cases"][0]["case_id"] == ACUTE_EXERCISE_EVAL


def test_acute_exercise_claim_boundary_and_no_prescription():
    claim = _acute_exercise_claim()
    blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
    meta = claim.get("metadata") or {}
    assert meta.get("claim_boundary")
    assert "边界" in claim.get("body", "")
    assert any(token in blob for token in ("发热", "疑似感染", "低强度恢复"))
    for banned in [
        "必须训练",
        "坚持训练",
        "高强度训练",
        "练狠一点",
        "运动治愈",
        "诊断为",
        "确诊",
        "自行服用抗生素",
        "自行服用退烧药后训练",
    ]:
        assert banned not in blob, f"{ACUTE_EXERCISE_CLAIM} 越界: {banned}"
