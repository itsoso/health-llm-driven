"""Golden retrieval and authority checks for the low-back health-evidence slice."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import app.services.clinical_claim_release as release_policy
import app.services.system_knowledge_service as knowledge_module
from app.models.system_knowledge import KBDocument
from app.services.health_evidence.authority import (
    route_authority_results as _route_authority_results,
)
from app.services.system_knowledge_eval import run_system_kb_eval_cases
from app.services.system_knowledge_importer import import_system_kb_artifacts


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
OFFICIAL_T1_HOSTS = {
    "www.nice.org.uk",
    "www.nhs.uk",
    "gravitas.acr.org",
    "www.who.int",
}


def route_authority_results(results, **kwargs):
    return _route_authority_results(
        results,
        serving_scope="health_evidence_runtime",
        **kwargs,
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


def test_low_back_pack_manifest_binds_exact_runtime_only_release_contract():
    manifest = json.loads(
        (SEED_DIR / "review_manifest.json").read_text(encoding="utf-8")
    )
    pack = next(
        item
        for item in manifest["authority_packs"]
        if item["domain"] == "low_back_pain"
    )

    assert set(pack["claim_ids"]) == CLAIM_IDS
    assert (
        pack["decision"]
        == "approved_for_health_evidence_runtime_by_product_owner"
    )
    assert pack["reviewer_role"] == "product_owner"
    assert pack["clinical_signoff"] == "not_claimed"
    assert (
        pack["serving_scope"]
        == release_policy.HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE
    )
    assert pack["serving_allowed"] is True
    assert pack["generic_serving_allowed"] is False
    assert (
        pack["source_policy"]
        == "T1 official guidance only; no raw Dedao or paid-course text"
    )
    assert (
        set(
            getattr(
                release_policy,
                "HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS",
                (),
            )
        )
        == set(pack["claim_ids"])
        == CLAIM_IDS
    )


def test_runtime_scope_requires_explicit_allowlist_even_when_not_globally_held(
    monkeypatch,
):
    claim_id = "claim:c_low_back_emergency_neurologic_red_flags"
    monkeypatch.setattr(
        release_policy,
        "CLINICAL_RELEASE_HOLD_DOCUMENT_IDS",
        frozenset(),
    )
    monkeypatch.setattr(
        release_policy,
        "HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS",
        frozenset(),
    )

    assert (
        release_policy.is_clinical_claim_serving_allowed(
            claim_id,
            release_policy.HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE,
        )
        is False
    )
    assert release_policy.is_clinical_claim_serving_allowed(claim_id) is True


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
            and urlparse(source.get("source") or "").scheme == "https"
            and urlparse(source.get("source") or "").hostname in OFFICIAL_T1_HOSTS
            and source.get("kind")
            and source.get("organization")
            and source.get("title")
            and source.get("version")
            for source in metadata["external_sources"]
        ), doc_id
        serialized = json.dumps(claim, ensure_ascii=False).lower()
        assert "dedao:" not in serialized, doc_id
        assert "paid_course_raw" not in serialized, doc_id
        assert "paid-course" not in serialized, doc_id


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


def test_runtime_scoped_low_back_queries_retrieve_only_the_released_claims(db):
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

    found_across_cases = set()
    for query, expected in cases.items():
        response = knowledge_module.search_health_evidence_runtime_claims(
            db,
            query,
            limit=10,
        )
        found = {
            (item.get("document") or {}).get("doc_id")
            for item in response.get("results") or []
        }
        assert found <= CLAIM_IDS, (query, found)
        assert expected <= found, (query, expected, found)
        found_across_cases.update(found)
    assert found_across_cases == CLAIM_IDS


def test_empty_runtime_release_allowlist_returns_zero_results(
    db,
    monkeypatch,
):
    sentinel = "EMPTY_RUNTIME_SCOPE_SENTINEL_4D2F"
    db.add(
        KBDocument(
            doc_id="claim:generic-reviewed-sentinel",
            doc_type="claim",
            title=sentinel,
            summary=sentinel,
            body=sentinel,
            confidence=0.99,
            evidence_level="A",
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.commit()
    monkeypatch.setattr(
        knowledge_module,
        "HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS",
        frozenset(),
    )

    response = knowledge_module.search_health_evidence_runtime_claims(
        db,
        sentinel,
        limit=10,
    )

    assert response["results"] == []


def test_low_back_golden_eval_cases_pass(db):
    _import_low_back_pack(db)

    report = run_system_kb_eval_cases(db, case_ids=EVAL_IDS)

    assert report["total"] == len(EVAL_IDS)
    assert report["failed"] == 0, report["cases"]


def test_low_back_eval_rejects_same_id_tampered_target_claim(db):
    _import_low_back_pack(db)
    claim = db.get(
        KBDocument,
        "claim:c_low_back_self_management_activity_boundary",
    )
    assert claim is not None
    claim.summary = "TAMPERED_SAME_ID_EVAL_TARGET"
    db.commit()

    report = run_system_kb_eval_cases(
        db,
        case_ids={"eval:low_back_self_management"},
    )

    assert report["failed"] == 1
    assert any(
        "missing_required_docs" in failure
        or "search_missing" in failure
        for failure in report["cases"][0]["failures"]
    )


def test_spoofed_eval_metadata_case_id_never_unlocks_runtime_search(db):
    spoofed_doc_id = "eval:spoofed-low-back-runtime"
    privileged_case_id = "eval:low_back_self_management"
    db.add(
        KBDocument(
            doc_id=spoofed_doc_id,
            doc_type="eval_case",
            title="Spoofed runtime eval",
            summary="metadata.case_id must not grant privileged retrieval",
            confidence=0.99,
            evidence_level="A",
            metadata_json={
                "review_status": "reviewed",
                "case_id": privileged_case_id,
                "input": {
                    "search_query": (
                        "普通急性腰痛 无红旗 继续活动 避免长期卧床"
                    ),
                },
                "expected": {
                    "search_query": (
                        "普通急性腰痛 无红旗 继续活动 避免长期卧床"
                    ),
                    "required_doc_ids": [
                        "claim:c_low_back_self_management_activity_boundary"
                    ],
                },
            },
        )
    )
    db.commit()

    report = run_system_kb_eval_cases(
        db,
        case_ids={spoofed_doc_id},
    )

    assert report["failed"] == 1
    assert "eval_case_identity_mismatch" in report["cases"][0]["failures"]
