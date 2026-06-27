"""Rhinitis sinusitis/asthma/immunotherapy referral-boundary KB tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_importer import import_system_kb_artifacts

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIMS_FILE = Path(SEED_DIR) / "claims.jsonl"

RHINITIS_REFERRAL_ENTITIES = {
    "sinusitis": "entity:condition:rhinosinusitis-risk",
    "asthma": "entity:condition:asthma-rhinitis-overlap",
    "immunotherapy": "entity:intervention:allergen-immunotherapy",
}

RHINITIS_REFERRAL_CLAIMS = {
    "sinusitis": "claim:c_rhinitis_sinusitis_referral_boundary",
    "asthma": "claim:c_rhinitis_asthma_overlap_referral_boundary",
    "immunotherapy": "claim:c_rhinitis_allergen_immunotherapy_referral_boundary",
}

RHINITIS_REFERRAL_CONTRAINDICATIONS = {
    "sinusitis": "contraindication:rhinitis_sinusitis_red_flags_no_self_treatment",
    "asthma": "contraindication:rhinitis_asthma_overlap_no_rhinitis_only_management",
    "immunotherapy": "contraindication:rhinitis_immunotherapy_no_self_start_or_escalation",
}

RHINITIS_REFERRAL_EVALS = {
    "sinusitis": "eval:rhinitis_sinusitis_referral_boundary",
    "asthma": "eval:rhinitis_asthma_overlap_referral_boundary",
    "immunotherapy": "eval:rhinitis_immunotherapy_referral_boundary",
}


def _claim(doc_id: str) -> dict[str, Any]:
    for line in CLAIMS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            return row
    raise AssertionError(f"missing seed claim: {doc_id}")


def _rhinitis_twin(conditions: list[str]):
    from app.twin.schema import ChronicConditionState, HealthTwin, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime(2026, 6, 27, tzinfo=UTC)))
    twin.chronic = ChronicConditionState(
        active_conditions=conditions,
        rhinitis_today={"active": True, "nasal_congestion": True},
    )
    return twin


def _condition_claim_ids_for_twin(db, twin) -> set[str]:
    from app.services.system_knowledge_service import (
        lookup_for_twin,
        system_kb_twin_payload_from_health_twin,
    )

    payload = system_kb_twin_payload_from_health_twin(twin)
    result = lookup_for_twin(db, payload)
    return {
        claim.get("doc_id")
        for claim in result.get("claims") or []
        if claim.get("match_type") == "condition"
    }


def test_rhinitis_referral_entities_claims_contraindications_and_eval_import(db):
    counts = import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_referral_import")
    assert counts["skipped_documents"] == 0

    doc_ids = (
        set(RHINITIS_REFERRAL_ENTITIES.values())
        | set(RHINITIS_REFERRAL_CLAIMS.values())
        | set(RHINITIS_REFERRAL_CONTRAINDICATIONS.values())
        | set(RHINITIS_REFERRAL_EVALS.values())
    )
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(doc_ids)).all()
    by_id = {doc.doc_id: doc for doc in docs}
    assert set(by_id) == doc_ids
    for doc_id in RHINITIS_REFERRAL_ENTITIES.values():
        assert by_id[doc_id].doc_type == "entity"
    for doc_id in RHINITIS_REFERRAL_CLAIMS.values():
        assert by_id[doc_id].doc_type == "claim"
    for doc_id in RHINITIS_REFERRAL_CONTRAINDICATIONS.values():
        assert by_id[doc_id].doc_type == "contraindication"
    for doc_id in RHINITIS_REFERRAL_EVALS.values():
        assert by_id[doc_id].doc_type == "eval_case"
    for doc in by_id.values():
        assert (doc.metadata_json or {}).get("review_status") == "reviewed", doc.doc_id


def test_rhinitis_sinusitis_referral_lookup_requires_sinusitis_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_sinusitis_lookup")

    risky = _rhinitis_twin(["过敏性鼻炎", "鼻窦炎", "面痛", "脓涕"])
    assert RHINITIS_REFERRAL_CLAIMS["sinusitis"] in _condition_claim_ids_for_twin(db, risky)

    rhinitis_only = _rhinitis_twin(["过敏性鼻炎"])
    assert RHINITIS_REFERRAL_CLAIMS["sinusitis"] not in _condition_claim_ids_for_twin(
        db, rhinitis_only
    )


def test_rhinitis_asthma_overlap_lookup_requires_lower_airway_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_asthma_lookup")

    risky = _rhinitis_twin(["过敏性鼻炎", "哮喘", "喘息", "夜间咳嗽"])
    assert RHINITIS_REFERRAL_CLAIMS["asthma"] in _condition_claim_ids_for_twin(db, risky)

    rhinitis_only = _rhinitis_twin(["过敏性鼻炎"])
    assert RHINITIS_REFERRAL_CLAIMS["asthma"] not in _condition_claim_ids_for_twin(
        db, rhinitis_only
    )


def test_rhinitis_immunotherapy_lookup_requires_immunotherapy_context(db):
    import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_immunotherapy_lookup")

    candidate = _rhinitis_twin(["过敏性鼻炎", "尘螨脱敏", "过敏原免疫治疗"])
    assert RHINITIS_REFERRAL_CLAIMS["immunotherapy"] in _condition_claim_ids_for_twin(
        db, candidate
    )

    rhinitis_only = _rhinitis_twin(["过敏性鼻炎"])
    assert RHINITIS_REFERRAL_CLAIMS["immunotherapy"] not in _condition_claim_ids_for_twin(
        db, rhinitis_only
    )


def test_system_kb_eval_runner_covers_rhinitis_referral_cases(db):
    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    import_system_kb_artifacts(db, SEED_DIR, actor="test:rhinitis_referral_eval")

    report = run_system_kb_eval_cases(db, case_ids=set(RHINITIS_REFERRAL_EVALS.values()))

    assert report["total"] == 3
    assert report["failed"] == 0, report
    assert {case["case_id"] for case in report["cases"]} == set(
        RHINITIS_REFERRAL_EVALS.values()
    )


def test_rhinitis_referral_claims_keep_actions_inside_referral_boundary():
    for doc_id in RHINITIS_REFERRAL_CLAIMS.values():
        claim = _claim(doc_id)
        blob = f"{claim.get('title','')} {claim.get('summary','')} {claim.get('body','')}"
        meta = claim.get("metadata") or {}
        assert meta.get("claim_boundary"), doc_id
        assert any(token in blob for token in ("耳鼻喉科", "过敏科", "医生", "转诊", "复核")), doc_id
        for banned in [
            "自行加量",
            "自行开始脱敏",
            "在家开始免疫治疗",
            "抗生素疗程",
            "长期使用减充血剂",
            "每日服用",
            "每天服用",
            "确诊",
            "诊断为",
            "你患有",
            "立即停药",
        ]:
            assert banned not in blob, f"{doc_id} 越界: {banned}"
