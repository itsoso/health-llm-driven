"""Exercise cardiac red-flag / low-recovery reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

EXERCISE_SAFETY_CLAIMS = {
    "cardiac_red_flags": "claim:c_exercise_cardiac_red_flags_stop_and_triage",
    "low_recovery": "claim:c_exercise_low_recovery_training_downgrade",
    "heat_illness": "claim:c_exercise_heat_illness_stop_and_cool_boundary",
}

EXERCISE_SAFETY_CONTRAINDICATIONS = {
    "cardiac_red_flags": "contraindication:exercise_cardiac_red_flags_no_training",
    "low_recovery": "contraindication:exercise_low_recovery_no_intensity_escalation",
    "heat_illness": "contraindication:exercise_heat_illness_no_training_or_delay",
}

EXERCISE_SAFETY_EVALS = {
    "cardiac_red_flags": "eval:exercise_cardiac_red_flags_boundary",
    "low_recovery": "eval:exercise_low_recovery_downgrade",
    "heat_illness": "eval:exercise_heat_illness_boundary",
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
    conditions: list[str] | None = None,
    training_readiness_score: int | None = None,
    training_readiness_level: str | None = None,
):
    from app.twin.schema import ChronicConditionState, HealthTwin, PhysiologicalState, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 6, 27, tzinfo=UTC)))
    if conditions:
        twin.chronic = ChronicConditionState(active_conditions=conditions)
    if training_readiness_score is not None or training_readiness_level is not None:
        twin.physiological = PhysiologicalState(
            training_readiness_score=training_readiness_score,
            training_readiness_level=training_readiness_level,
        )
    return twin


def _claim_ids_for_twin(db, twin) -> set[str]:
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    payload = system_kb_twin_payload_from_health_twin(twin)
    result = lookup_for_twin(db, payload)
    return {claim.get("doc_id") for claim in result.get("claims") or []}


def test_exercise_safety_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:exercise_safety_import")
    assert counts["skipped_documents"] == 0

    doc_ids = (
        set(EXERCISE_SAFETY_CLAIMS.values())
        | set(EXERCISE_SAFETY_CONTRAINDICATIONS.values())
        | set(EXERCISE_SAFETY_EVALS.values())
    )
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in EXERCISE_SAFETY_CLAIMS.values():
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in EXERCISE_SAFETY_CONTRAINDICATIONS.values():
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in EXERCISE_SAFETY_EVALS.values():
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_exercise_cardiac_red_flag_lookup_requires_red_flag_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:exercise_cardiac_lookup")

    risky = _twin(conditions=["运动中胸痛", "心悸"])
    assert EXERCISE_SAFETY_CLAIMS["cardiac_red_flags"] in _claim_ids_for_twin(db, risky)

    no_red_flag = _twin(conditions=["普通肌肉酸痛"])
    assert EXERCISE_SAFETY_CLAIMS["cardiac_red_flags"] not in _claim_ids_for_twin(db, no_red_flag)


def test_low_recovery_lookup_requires_low_training_readiness(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:exercise_low_recovery_lookup")

    low_recovery = _twin(training_readiness_score=20, training_readiness_level="poor")
    assert EXERCISE_SAFETY_CLAIMS["low_recovery"] in _claim_ids_for_twin(db, low_recovery)

    ready = _twin(training_readiness_score=72, training_readiness_level="high")
    assert EXERCISE_SAFETY_CLAIMS["low_recovery"] not in _claim_ids_for_twin(db, ready)


def test_heat_illness_lookup_requires_heat_exertion_and_symptom_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:exercise_heat_illness_lookup")

    risky = _twin(conditions=["高温户外跑", "头晕", "恶心"])
    assert EXERCISE_SAFETY_CLAIMS["heat_illness"] in _claim_ids_for_twin(db, risky)

    heat_only = _twin(conditions=["高温户外散步"])
    assert EXERCISE_SAFETY_CLAIMS["heat_illness"] not in _claim_ids_for_twin(db, heat_only)


def test_system_kb_eval_runner_covers_exercise_safety_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:exercise_safety_eval")

    report = run_system_kb_eval_cases(db, case_ids=set(EXERCISE_SAFETY_EVALS.values()))

    assert report["total"] == 3
    assert report["failed"] == 0, report
    assert {case["case_id"] for case in report["cases"]} == set(EXERCISE_SAFETY_EVALS.values())


def test_exercise_safety_claims_keep_actions_in_clinician_boundary():
    for doc_id in EXERCISE_SAFETY_CLAIMS.values():
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("医生", "就医", "红旗", "降级", "边界")), doc_id
        for banned in [
            "必须训练",
            "坚持训练",
            "高强度训练",
            "练狠一点",
            "运动治愈",
            "诊断为",
            "确诊",
            "自行服用",
            "冲刺",
        ]:
            assert banned not in blob, f"{doc_id} 越界: {banned}"
