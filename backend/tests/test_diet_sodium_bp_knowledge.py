"""High-sodium diet / blood-pressure reviewed-KB integration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

SODIUM_BP_CLAIM = "claim:c_high_sodium_bp_food_swap_boundary"
SODIUM_BP_CONTRAINDICATION = (
    "contraindication:high_sodium_bp_no_med_adjustment_or_extreme_restriction"
)
SODIUM_BP_EVAL = "eval:high_sodium_bp_food_swap_boundary"


def _high_sodium_bp_twin():
    from app.twin.schema import BehavioralState, GoalsContext, HealthTwin, LabsContext, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.labs = LabsContext(blood_pressure_systolic=138, blood_pressure_diastolic=86)
    twin.goals = GoalsContext(
        active_goals=[
            {"type": "metabolic_health", "title": "控制血压和代谢健康"},
        ],
        active_goals_count=1,
    )
    twin.behavioral = BehavioralState(
        diet_sodium_mg_today=3600,
        high_sodium_foods_today=["外卖盖饭", "酱菜"],
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


def test_high_sodium_bp_claim_contraindication_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_sodium_bp")
    assert counts["skipped_documents"] == 0

    docs = db.query(KBDocument).filter(
        KBDocument.doc_id.in_({
            SODIUM_BP_CLAIM,
            SODIUM_BP_CONTRAINDICATION,
            SODIUM_BP_EVAL,
        })
    ).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == {SODIUM_BP_CLAIM, SODIUM_BP_CONTRAINDICATION, SODIUM_BP_EVAL}
    assert by_id[SODIUM_BP_CLAIM].doc_type == "claim"
    assert by_id[SODIUM_BP_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[SODIUM_BP_EVAL].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed"


def test_high_sodium_bp_twin_maps_to_kb_payload_and_lookup(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_sodium_bp_lookup")

    payload = system_kb_twin_payload_from_health_twin(_high_sodium_bp_twin())
    assert payload["labs"]["systolic_bp"] == 138
    assert payload["labs"]["diastolic_bp"] == 86
    assert payload["behavioral"]["diet_sodium_mg_today"] == 3600
    assert payload["behavioral"]["high_sodium_foods_today"] == ["外卖盖饭", "酱菜"]
    assert payload["goals"]["metabolic_health"]["active"] is True

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert SODIUM_BP_CLAIM in claim_ids


def test_system_kb_eval_runner_covers_high_sodium_bp_case(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:diet_sodium_bp_eval")

    report = run_system_kb_eval_cases(db, case_ids={SODIUM_BP_EVAL})

    assert report["total"] == 1
    assert report["failed"] == 0, report
    assert report["cases"][0]["case_id"] == SODIUM_BP_EVAL


def test_high_sodium_bp_claim_boundary_and_no_prescription():
    claim = _claim(SODIUM_BP_CLAIM)
    blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
    meta = claim.get("metadata") or {}
    assert meta.get("claim_boundary")
    assert "边界" in claim.get("body", "")
    assert any(token in blob for token in ("营养标签", "外卖", "家庭血压", "医生"))
    for banned in [
        "自行停药",
        "自行减药",
        "自行加药",
        "降压药减半",
        "直接停用",
        "无盐饮食",
        "完全不吃盐",
        "确诊",
        "诊断为",
    ]:
        assert banned not in blob, f"{SODIUM_BP_CLAIM} 越界: {banned}"
