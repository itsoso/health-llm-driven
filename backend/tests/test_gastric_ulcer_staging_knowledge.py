"""Reviewed-KB regression for the gastric-ulcer staging-vs-bleeding-grading claim.

Guards the concept fix caught by the comparative eval (`fact_gastric_ulcer_stages`):
the assistant conflated Sakita-Miwa healing staging (A1/A2/H1/H2/S1/S2, a healing
timeline) with the Forrest classification (Ⅰ-Ⅲ, endoscopic bleeding stigmata /
rebleeding risk). There is no hardcoded staging template in code — the fix is the
owner-reviewed claim, so this test proves it imports reviewed and is retrievable
on both the Twin-gated path and the free-text FTS path (the bare-fact question).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = SEED_DIR / "claims.jsonl"

STAGING_CLAIM = "claim:c_gastric_ulcer_staging_systems_distinction"


def _claim(doc_id: str) -> dict[str, Any]:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _ulcer_twin():
    from app.twin.schema import ChronicConditionState, HealthTwin, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 7, 6, tzinfo=UTC)))
    twin.chronic = ChronicConditionState(active_conditions=["消化性溃疡"])
    return twin


def _claim_ids_for_twin(db, twin) -> set[str]:
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    payload = system_kb_twin_payload_from_health_twin(twin)
    result = lookup_for_twin(db, payload)
    return {claim.get("doc_id") for claim in result.get("claims") or []}


def test_staging_claim_imports_reviewed(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:gastric_staging_import")

    doc = db.query(KBDocument).filter(KBDocument.doc_id == STAGING_CLAIM).one_or_none()
    assert doc is not None, "staging claim was skipped on import"
    assert doc.doc_type == "claim"
    assert (doc.metadata_json or {}).get("review_status") == "reviewed"


def test_staging_claim_surfaces_for_ulcer_twin(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:gastric_staging_twin")
    assert STAGING_CLAIM in _claim_ids_for_twin(db, _ulcer_twin())


def test_staging_claim_retrievable_by_free_text(db):
    """The bare-fact question ('胃溃疡有哪几个阶段…') hits the FTS path, not Twin gating."""
    from app.services.system_knowledge_service import (
        reindex_knowledge_documents,
        search_knowledge,
    )

    import_system_kb_artifacts(db, SEED_DIR, actor="test:gastric_staging_search")
    reindex_knowledge_documents(db, actor="test:gastric_staging_search")

    result = search_knowledge(
        db,
        "胃溃疡 分期 阶段 愈合期 瘢痕期 Forrest 出血 分级",
        limit=10,
        doc_type="claim",
    )
    ids = {
        (item.get("document") or {}).get("doc_id")
        for item in (result.get("results") or [])
    }
    assert STAGING_CLAIM in ids, ids


def test_staging_claim_distinguishes_systems_within_r4_boundary():
    claim = _claim(STAGING_CLAIM)
    blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
    meta = claim.get("metadata") or {}

    # actually distinguishes the two systems (the whole point of the fix)
    assert "Sakita" in blob or "崎田" in blob, "must name Sakita-Miwa healing staging"
    assert "Forrest" in blob, "must name Forrest bleeding classification"
    assert any(t in blob for t in ("A1", "H1", "S1")), "must reference healing-stage letters"
    assert any(t in blob for t in ("不可互换", "概念错误", "两套")), "must state the two are not interchangeable"

    # R4 clinician boundary present, no imperative/prescription/diagnosis language
    assert meta.get("claim_boundary")
    assert any(t in blob for t in ("医生", "消化科", "内镜医生", "边界", "不下诊断"))
    for banned in [
        "自行停药",
        "自行换药",
        "自行调整",
        "直接停用",
        "推荐剂量",
        "每日服用",
        "每天服用",
        "确诊",
        "四联",
        "阿莫西林",
        "克拉霉素",
        "甲硝唑",
    ]:
        assert banned not in blob, f"{STAGING_CLAIM} 越界: {banned}"
