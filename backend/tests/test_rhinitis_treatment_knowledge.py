"""Chronic/allergic rhinitis treatment-boundary reviewed KB tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

RHINITIS_TREATMENT_CLAIM = (
    "claim:c_chronic_rhinitis_intranasal_steroid_saline_boundary"
)
RHINITIS_TREATMENT_CONTRAINDICATION = (
    "contraindication:rhinitis_decongestant_overuse_no_self_escalation"
)
RHINITIS_TREATMENT_EVAL = "eval:chronic_rhinitis_treatment_boundary"


def _rhinitis_twin():
    from app.twin.schema import (
        BehavioralState,
        ChronicConditionState,
        HealthTwin,
        TwinMeta,
    )

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.behavioral = BehavioralState(
        sneeze_count_today=18,
        nasal_wash_count_today=0,
    )
    twin.chronic = ChronicConditionState(
        active_conditions=["过敏性鼻炎"],
        rhinitis_today={"active": True, "nasal_congestion": True},
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


def test_rhinitis_treatment_claim_contraindication_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_treatment")
    assert counts["skipped_documents"] == 0

    docs = db.query(KBDocument).filter(
        KBDocument.doc_id.in_({
            RHINITIS_TREATMENT_CLAIM,
            RHINITIS_TREATMENT_CONTRAINDICATION,
            RHINITIS_TREATMENT_EVAL,
        })
    ).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == {
        RHINITIS_TREATMENT_CLAIM,
        RHINITIS_TREATMENT_CONTRAINDICATION,
        RHINITIS_TREATMENT_EVAL,
    }
    assert by_id[RHINITIS_TREATMENT_CLAIM].doc_type == "claim"
    assert by_id[RHINITIS_TREATMENT_CONTRAINDICATION].doc_type == "contraindication"
    assert by_id[RHINITIS_TREATMENT_EVAL].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed"

    contraindication_meta = by_id[RHINITIS_TREATMENT_CONTRAINDICATION].metadata_json or {}
    blocks = set(contraindication_meta.get("blocks") or [])
    assert "decongestant_overuse" in blocks
    assert "self_escalate_rhinitis_medication" in blocks


def test_rhinitis_twin_maps_to_kb_payload_and_lookup(db):
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_treatment_lookup")

    payload = system_kb_twin_payload_from_health_twin(_rhinitis_twin())
    assert payload["conditions"]["rhinitis"]["active"] is True
    assert payload["conditions"]["active"] == ["过敏性鼻炎"]

    result = lookup_for_twin(db, payload)
    claim_ids = {claim.get("doc_id") for claim in result.get("claims") or []}
    assert RHINITIS_TREATMENT_CLAIM in claim_ids


def test_rhinitis_treatment_claim_is_retrievable(db):
    from app.services.system_knowledge_service import (
        reindex_knowledge_documents,
        search_knowledge,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_treatment_search")
    reindex_knowledge_documents(db, actor="test:rhinitis_treatment_search")

    result = search_knowledge(
        db,
        "过敏性鼻炎 鼻喷激素 生理盐水 冲洗 减充血剂 反跳 耳鼻喉科",
        limit=12,
        doc_type="claim",
    )
    ids = {
        (item.get("document") or {}).get("doc_id")
        for item in (result.get("results") or [])
    }
    assert RHINITIS_TREATMENT_CLAIM in ids, ids


def test_system_kb_eval_runner_covers_rhinitis_treatment_case(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_treatment_eval")

    report = run_system_kb_eval_cases(db, case_ids={RHINITIS_TREATMENT_EVAL})

    assert report["total"] == 1
    assert report["failed"] == 0, report
    assert report["cases"][0]["case_id"] == RHINITIS_TREATMENT_EVAL


def test_rhinitis_treatment_claim_boundary_and_no_prescription():
    claim = _claim(RHINITIS_TREATMENT_CLAIM)
    blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
    meta = claim.get("metadata") or {}
    assert meta.get("claim_boundary")
    assert "边界" in claim.get("body", "")
    assert any(token in blob for token in ("鼻喷激素", "生理盐水", "抗组胺", "医生", "耳鼻喉科"))
    for banned in [
        "自行加量",
        "连续使用减充血剂",
        "鼻喷剂越多越好",
        "确诊",
        "诊断为",
        "你患有",
        "立即停药",
        "每日服用",
        "每天服用",
    ]:
        assert banned not in blob, f"{RHINITIS_TREATMENT_CLAIM} 越界: {banned}"
