from __future__ import annotations

import json

from app.services.system_kb.dedao_authority_import import (
    HEALTH_AUTHORITY_PACK_CONTRACT,
    dry_run_import_dedao_authority_pack,
)


def _line(**overrides):
    payload = {
        "consumer_contract": HEALTH_AUTHORITY_PACK_CONTRACT,
        "project_id": "health",
        "target_system": "health-llm-driven",
        "claim_id": "dedao:book-1:claim-1",
        "book_id": "book-1",
        "book_title": "健康学习材料",
        "chapter_id": "chapter-1",
        "title": "睡眠复盘支持健康管理",
        "summary": "稳定复盘帮助识别睡眠行为模式。",
        "candidate_type": "education_context_candidate",
        "allowed_uses": ["health_education", "question_preparation", "context_retrieval"],
        "blocked_uses": ["diagnosis", "treatment", "dosage", "medication_change", "emergency_guidance"],
        "risk_tier": "assistive_only",
        "decision": "assist",
        "citations": ["citation-1"],
        "source_hash": "source-hash-1",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_dry_run_rejects_unknown_contract():
    report = dry_run_import_dedao_authority_pack(
        [
            _line(consumer_contract="dedao_project_collection_jsonl_v1"),
        ],
    )

    assert report.total == 1
    assert report.accepted_for_review == []
    assert report.invalid[0].reason == "unknown_contract"


def test_dry_run_blocks_medication_action_claim():
    report = dry_run_import_dedao_authority_pack(
        [
            _line(
                claim_id="dedao:book-1:claim-medication",
                title="用药剂量需要医生判断",
                summary="不能根据单一书摘自行调整药物剂量。",
                allowed_uses=["health_education", "action_support"],
                blocked_uses=["diagnosis", "treatment", "dosage", "medication_change", "emergency_guidance"],
            ),
        ],
    )

    assert report.accepted_for_review == []
    assert report.blocked[0].claim_id == "dedao:book-1:claim-medication"
    assert report.blocked[0].reason == "medical_action_claim"


def test_dry_run_reports_review_candidates_without_writing(tmp_path):
    report = dry_run_import_dedao_authority_pack(
        [
            _line(claim_id="dedao:book-1:claim-1", source_hash="source-hash-1"),
            _line(claim_id="dedao:book-1:claim-1", source_hash="source-hash-1"),
            _line(claim_id="dedao:book-1:claim-missing-source", source_hash="", citations=[]),
        ],
    )

    assert [item.claim_id for item in report.accepted_for_review] == ["dedao:book-1:claim-1"]
    assert report.duplicates[0].claim_id == "dedao:book-1:claim-1"
    assert report.missing_source_refs[0].claim_id == "dedao:book-1:claim-missing-source"
    assert report.would_write is False
    assert not any(tmp_path.iterdir())
