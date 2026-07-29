"""Golden retrieval and authority checks for the low-back health-evidence slice."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import app.services.health_evidence.authority as authority_module
import app.services.system_knowledge_service as knowledge_module
from app.models.system_knowledge import KBDocument
from app.services.health_evidence.authority import route_authority_results
from app.services.system_knowledge_eval import run_system_kb_eval_cases
from app.services.system_knowledge_importer import import_system_kb_artifacts
from app.services.system_knowledge_service import search_knowledge


SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
CLAIM_IDS = {
    "claim:c_low_back_emergency_neurologic_red_flags",
    "claim:c_low_back_serious_cause_screening_boundary",
    "claim:c_low_back_self_management_activity_boundary",
    "claim:c_low_back_imaging_not_routine_boundary",
    "claim:c_chronic_low_back_holistic_care_boundary",
}
EVAL_IDS = {
    "eval:low_back_neurologic_red_flags",
    "eval:low_back_self_management",
    "eval:low_back_imaging_boundary",
    "eval:chronic_low_back_holistic_care",
}
NOW = datetime(2026, 7, 29, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _exercise_offline_candidate_pack_behind_release_hold(monkeypatch):
    """Golden authoring checks are offline; production serving stays held."""

    monkeypatch.setattr(
        authority_module,
        "is_clinical_claim_serving_allowed",
        lambda _doc_id: True,
    )
    monkeypatch.setattr(
        knowledge_module,
        "CLINICAL_RELEASE_HOLD_CLAIM_IDS",
        frozenset(),
    )


def _jsonl_rows(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (SEED_DIR / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _import_low_back_pack(db) -> None:
    counts = import_system_kb_artifacts(
        db,
        SEED_DIR,
        actor="test:low_back_health_evidence",
    )
    assert counts["skipped_documents"] == 0


def test_low_back_claims_are_reviewed_t1_and_never_depend_on_raw_dedao():
    claims = {
        row["doc_id"]: row
        for row in _jsonl_rows("claims.jsonl")
        if row.get("doc_id") in CLAIM_IDS
    }

    assert set(claims) == CLAIM_IDS
    for doc_id, claim in claims.items():
        metadata = claim["metadata"]
        assert metadata["review_status"] == "reviewed", doc_id
        assert metadata["license_scope"] == "internal_transformed_claims", doc_id
        assert metadata["authority_tier"] == "T1", doc_id
        assert metadata["review_valid_until"] >= "2027-07-29", doc_id
        applicability = metadata["applicability"]
        assert "low_back_pain" in applicability["domains"], doc_id
        assert applicability["risk_levels"], doc_id
        assert applicability["populations"] == ["adults_16_plus"], doc_id
        assert applicability["use_cases"], doc_id
        assert metadata["external_sources"], doc_id
        assert all(
            source.get("review_status") == "reviewed"
            and source.get("source")
            and source.get("kind")
            and source.get("organization")
            and source.get("title")
            and source.get("version")
            for source in metadata["external_sources"]
        ), doc_id
        serialized = json.dumps(claim, ensure_ascii=False).lower()
        assert "dedao:" not in serialized, doc_id
        assert "paid_course_raw" not in serialized, doc_id


def test_low_back_pack_authority_gate_enforces_exact_applicability_context(db):
    _import_low_back_pack(db)
    documents = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id.in_(CLAIM_IDS))
        .order_by(KBDocument.doc_id.asc())
        .all()
    )
    results = [
        {
            "document": {
                "doc_id": document.doc_id,
                "doc_type": document.doc_type,
                "title": document.title,
                "summary": document.summary,
                "body": document.body,
                "sources": document.sources,
                "metadata": document.metadata_json,
            }
        }
        for document in documents
    ]

    contexts = {
        ("emergency", "symptom_triage"): {
            "claim:c_low_back_emergency_neurologic_red_flags",
        },
        ("high", "initial_assessment"): {
            "claim:c_low_back_serious_cause_screening_boundary",
        },
        ("medium", "initial_assessment"): {
            "claim:c_low_back_serious_cause_screening_boundary",
        },
        ("medium", "self_management_after_red_flag_screen"): {
            "claim:c_low_back_self_management_activity_boundary",
        },
        ("medium", "imaging_decision"): {
            "claim:c_low_back_imaging_not_routine_boundary",
        },
        ("medium", "chronic_primary_care"): {
            "claim:c_chronic_low_back_holistic_care_boundary",
        },
    }

    for (risk_level, use_case), expected_ids in contexts.items():
        bundle = route_authority_results(
            results,
            domain="low_back_pain",
            risk_level=risk_level,
            population="adults_16_plus",
            use_case=use_case,
            now=NOW,
        )
        assert {item.doc_id for item in bundle.accepted} == expected_ids
        assert all(source.authority_tier == "T1" for source in bundle.accepted)


def test_low_back_pack_rejects_unconfirmed_population_and_use_case(db):
    _import_low_back_pack(db)
    document = (
        db.query(KBDocument)
        .filter(
            KBDocument.doc_id
            == "claim:c_low_back_self_management_activity_boundary"
        )
        .one()
    )
    result = {
        "document": {
            "doc_id": document.doc_id,
            "title": document.title,
            "summary": document.summary,
            "sources": document.sources,
            "metadata": document.metadata_json,
        }
    }

    for population, use_case, expected_reason in (
        (None, "self_management_after_red_flag_screen", "missing_population_context"),
        ("adults_16_plus", None, "missing_use_case_context"),
        ("pediatric", "self_management_after_red_flag_screen", "wrong_population"),
        ("adults_16_plus", "initial_assessment", "wrong_use_case"),
    ):
        bundle = route_authority_results(
            [result],
            domain="low_back_pain",
            risk_level="medium",
            population=population,
            use_case=use_case,
            now=NOW,
        )
        assert bundle.accepted == ()
        assert bundle.rejections[0].reason == expected_reason


def test_low_back_queries_retrieve_the_expected_reviewed_claims(db):
    _import_low_back_pack(db)
    cases = {
        "腰痛 大小便失禁 会阴麻木 双腿无力 急诊": {
            "claim:c_low_back_emergency_neurologic_red_flags"
        },
        "腰疼 发热 体重下降 严重外伤 需要就医": {
            "claim:c_low_back_serious_cause_screening_boundary"
        },
        "普通急性腰痛 继续活动 避免长期卧床 自我管理": {
            "claim:c_low_back_self_management_activity_boundary"
        },
        "腰痛 是否需要立刻拍片 MRI 影像检查": {
            "claim:c_low_back_imaging_not_routine_boundary"
        },
        "慢性腰痛 超过三个月 整体评估 多模式康复": {
            "claim:c_chronic_low_back_holistic_care_boundary"
        },
    }

    for query, expected in cases.items():
        response = search_knowledge(db, query, limit=10, doc_type="claim")
        found = {
            (item.get("document") or {}).get("doc_id")
            for item in response.get("results") or []
        }
        assert expected <= found, (query, expected, found)


def test_low_back_golden_eval_cases_pass(db):
    _import_low_back_pack(db)

    report = run_system_kb_eval_cases(db, case_ids=EVAL_IDS)

    assert report["total"] == len(EVAL_IDS)
    assert report["failed"] == 0, report["cases"]
