"""Fail-closed authority gate for user-visible health evidence."""

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

import app.services.health_evidence.authority as authority_module
from app.services.health_evidence.authority import (
    route_authority_results as _route_authority_results,
)


NOW = datetime(2026, 7, 29, tzinfo=UTC)
SEED_CLAIMS = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "system_kb_v2_seed"
    / "claims.jsonl"
)


def route_authority_results(results, **kwargs):
    return _route_authority_results(
        results,
        serving_scope="health_evidence_runtime",
        **kwargs,
    )

def _seed_claim(doc_id: str) -> dict:
    for line in SEED_CLAIMS.read_text(encoding="utf-8").splitlines():
        claim = json.loads(line)
        if claim.get("doc_id") == doc_id:
            return claim
    raise AssertionError(f"missing seed claim: {doc_id}")


def _result(
    *,
    doc_id: str = "claim:c_low_back_serious_cause_screening_boundary",
    review_status: str = "reviewed",
    license_scope: str = "internal_transformed_claims",
    authority_tier: str = "T1",
    review_valid_until: str = "2027-07-29T00:00:00+00:00",
    domains: list[str] | None = None,
    risk_levels: list[str] | None = None,
    populations: list[str] | None = None,
    use_cases: list[str] | None = None,
    sources: list[str] | None = None,
    external_sources: list[dict] | None = None,
) -> dict:
    claim = deepcopy(
        _seed_claim("claim:c_low_back_serious_cause_screening_boundary")
    )
    claim["doc_id"] = doc_id
    metadata = claim["metadata"]
    metadata["review_status"] = review_status
    metadata["license_scope"] = license_scope
    metadata["authority_tier"] = authority_tier
    metadata["review_valid_until"] = review_valid_until
    applicability = metadata["applicability"]
    if domains is not None:
        applicability["domains"] = domains
    if risk_levels is not None:
        applicability["risk_levels"] = risk_levels
    if populations is not None:
        applicability["populations"] = populations
    if use_cases is not None:
        applicability["use_cases"] = use_cases
    if sources is not None:
        claim["sources"] = sources
    if external_sources is not None:
        metadata["external_sources"] = external_sources
    return {
        "score": 0.91,
        "document": claim,
    }


def test_accepts_fresh_reviewed_applicable_t1_evidence():
    bundle = route_authority_results(
        [_result()],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    assert bundle.status == "sufficient"
    assert [item.doc_id for item in bundle.accepted] == [
        "claim:c_low_back_serious_cause_screening_boundary"
    ]
    assert bundle.accepted[0].authority_tier == "T1"
    assert bundle.rejections == ()


def test_default_release_policy_can_hold_an_otherwise_valid_claim(monkeypatch):
    monkeypatch.setattr(
        authority_module,
        "is_clinical_claim_serving_allowed",
        lambda _doc_id, _serving_scope: False,
    )

    bundle = route_authority_results(
        [_result()],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    assert bundle.accepted == ()
    assert bundle.rejections[0].reason == "clinical_review_pending"


def test_rejects_every_missing_authority_dimension_fail_closed():
    cases = {
        "unreviewed": _result(review_status="draft"),
        "disallowed_license": _result(license_scope="paid_course_raw"),
        "missing_tier": _result(authority_tier=""),
        "stale": _result(review_valid_until="2026-07-28T23:59:59+00:00"),
        "wrong_domain": _result(domains=["cardiovascular"]),
        "missing_risk_applicability": _result(risk_levels=[]),
        "missing_population_applicability": _result(populations=[]),
        "missing_use_case_applicability": _result(use_cases=[]),
        "missing_source_id": _result(sources=[]),
        "missing_source_registry": _result(external_sources=[]),
    }

    for expected_reason, result in cases.items():
        bundle = route_authority_results(
            [result],
            domain="low_back_pain",
            risk_level="medium",
            population="adults_16_plus",
            use_case="initial_assessment",
            now=NOW,
        )
        assert bundle.accepted == (), expected_reason
        assert bundle.status == "insufficient", expected_reason
        assert bundle.rejections[0].reason == expected_reason


def test_medium_risk_rejects_education_only_tier():
    bundle = route_authority_results(
        [_result(authority_tier="T3")],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    assert bundle.accepted == ()
    assert bundle.rejections[0].reason == "tier_not_allowed_for_risk"


def test_rejects_self_declared_dedao_paid_course_even_when_marked_t1():
    paid_course = _result(
        doc_id="claim:forged_paid_course",
        risk_levels=["emergency"],
        use_cases=["symptom_triage"],
        sources=["dedao:paid-course"],
        external_sources=[
            {
                "source": "https://www.dedao.cn/course/paid",
                "kind": "course",
                "organization": "Dedao",
                "title": "付费腰痛课",
                "version": "2026",
                "review_status": "reviewed",
            }
        ],
    )

    bundle = route_authority_results(
        [paid_course],
        domain="low_back_pain",
        risk_level="emergency",
        population="adults_16_plus",
        use_case="symptom_triage",
        now=NOW,
    )

    assert bundle.accepted == ()
    assert bundle.rejections[0].reason == "untrusted_source_id"


def test_rejects_source_identity_fields_that_do_not_match_registry():
    cases = {
        "source_url": _result(
            external_sources=[
                {
                    "source": "https://www.nice.org.uk.evil.example/guidance/ng59",
                    "kind": "guideline",
                    "organization": "NICE",
                    "title": "Forged NICE host",
                    "version": "2026",
                    "review_status": "reviewed",
                }
            ]
        ),
        "organization": _result(
            external_sources=[
                {
                    "source": "https://www.nice.org.uk/guidance/ng59",
                    "kind": "guideline",
                    "organization": "Dedao",
                    "title": "Forged publisher",
                    "version": "2026",
                    "review_status": "reviewed",
                }
            ]
        ),
        "kind": _result(
            external_sources=[
                {
                    "source": "https://www.nice.org.uk/guidance/ng59",
                    "kind": "course",
                    "organization": "NICE",
                    "title": "Forged source kind",
                    "version": "2026",
                    "review_status": "reviewed",
                }
            ]
        ),
    }

    for field, result in cases.items():
        bundle = route_authority_results(
            [result],
            domain="low_back_pain",
            risk_level="medium",
            population="adults_16_plus",
            use_case="initial_assessment",
            now=NOW,
        )
        assert bundle.accepted == (), field
        assert bundle.rejections[0].reason == "source_identity_mismatch", field


def test_rejects_source_title_or_version_that_is_not_registry_canonical():
    canonical = {
        "source": "https://www.nice.org.uk/guidance/ng59",
        "kind": "guideline",
        "organization": "NICE",
        "title": "Low back pain and sciatica in over 16s: assessment and management",
        "version": "NG59 updated 2020-12-11",
        "review_status": "reviewed",
    }
    cases = {
        "title": {**canonical, "title": "得到付费腰痛课"},
        "version": {**canonical, "version": "自报 2026 权威版"},
    }

    for field, source in cases.items():
        bundle = route_authority_results(
            [_result(external_sources=[source])],
            domain="low_back_pain",
            risk_level="medium",
            population="adults_16_plus",
            use_case="initial_assessment",
            now=NOW,
        )
        assert bundle.accepted == (), field
        assert bundle.rejections[0].reason == "source_identity_mismatch", field


def test_rejects_when_document_and_external_source_registry_are_not_bijective():
    result = _result(
        sources=["nice:ng59", "nhs:back-pain-2026"],
        external_sources=[
            {
                "source": "https://www.nice.org.uk/guidance/ng59",
                "kind": "guideline",
                "organization": "NICE",
                "title": "Low back pain and sciatica in over 16s: assessment and management",
                "version": "NG59 updated 2020-12-11",
                "review_status": "reviewed",
            }
        ],
    )

    bundle = route_authority_results(
        [result],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    assert bundle.accepted == ()
    assert bundle.rejections[0].reason == "source_registry_mismatch"


def test_rejects_self_declared_tier_that_disagrees_with_registry():
    bundle = route_authority_results(
        [_result(authority_tier="T2")],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    assert bundle.accepted == ()
    assert bundle.rejections[0].reason == "authority_tier_mismatch"


@pytest.mark.parametrize("tampered_field", ["summary", "body"])
def test_rejects_tampered_claim_and_never_releases_its_text(tampered_field):
    forged = deepcopy(
        _seed_claim("claim:c_low_back_serious_cause_screening_boundary")
    )
    malicious_text = "建议卧床三天，并自行服用布洛芬 800 毫克，每日三次。"
    forged[tampered_field] = malicious_text

    bundle = route_authority_results(
        [{"document": forged}],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    assert bundle.accepted == ()
    assert bundle.rejections[0].reason == "claim_artifact_mismatch"
    assert malicious_text not in bundle.to_prompt()


def test_rejects_unpublished_claim_even_when_it_copies_an_official_source():
    unpublished = deepcopy(
        _seed_claim("claim:c_low_back_serious_cause_screening_boundary")
    )
    unpublished["doc_id"] = "claim:forged_official_looking_advice"

    bundle = route_authority_results(
        [{"document": unpublished}],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    assert bundle.accepted == ()
    assert bundle.rejections[0].reason == "untrusted_claim_id"


def test_claim_cannot_widen_its_published_applicability_metadata():
    attacks = {
        "risk": {
            "field": "risk_levels",
            "extra": "emergency",
            "risk_level": "emergency",
            "population": "adults_16_plus",
            "use_case": "initial_assessment",
        },
        "population": {
            "field": "populations",
            "extra": "pediatric",
            "risk_level": "medium",
            "population": "pediatric",
            "use_case": "initial_assessment",
        },
        "use_case": {
            "field": "use_cases",
            "extra": "self_management_after_red_flag_screen",
            "risk_level": "medium",
            "population": "adults_16_plus",
            "use_case": "self_management_after_red_flag_screen",
        },
    }

    for dimension, attack in attacks.items():
        forged = _result()["document"]
        applicability = forged["metadata"]["applicability"]
        applicability[attack["field"]] = [
            *applicability[attack["field"]],
            attack["extra"],
        ]
        bundle = route_authority_results(
            [{"document": forged}],
            domain="low_back_pain",
            risk_level=attack["risk_level"],
            population=attack["population"],
            use_case=attack["use_case"],
            now=NOW,
        )
        assert bundle.accepted == (), dimension
        assert bundle.rejections[0].reason == "claim_policy_mismatch", dimension


def test_rejects_when_required_runtime_applicability_context_is_missing():
    cases = {
        "missing_risk_context": {
            "risk_level": "",
            "population": "adults_16_plus",
            "use_case": "initial_assessment",
        },
        "missing_population_context": {
            "risk_level": "medium",
            "population": None,
            "use_case": "initial_assessment",
        },
        "missing_use_case_context": {
            "risk_level": "medium",
            "population": "adults_16_plus",
            "use_case": None,
        },
    }

    for expected_reason, context in cases.items():
        bundle = route_authority_results(
            [_result()],
            domain="low_back_pain",
            risk_level=context["risk_level"],
            population=context["population"],
            use_case=context["use_case"],
            now=NOW,
        )
        assert bundle.accepted == (), expected_reason
        assert bundle.rejections[0].reason == expected_reason


def test_rejects_claim_outside_exact_risk_population_or_use_case():
    cases = {
        "wrong_risk": {
            "result": _result(risk_levels=["low"]),
            "population": "adults_16_plus",
            "use_case": "initial_assessment",
        },
        "wrong_population": {
            "result": _result(populations=["adults_16_plus"]),
            "population": "pediatric",
            "use_case": "initial_assessment",
        },
        "wrong_use_case": {
            "result": _result(use_cases=["initial_assessment"]),
            "population": "adults_16_plus",
            "use_case": "chronic_primary_care",
        },
    }

    for expected_reason, case in cases.items():
        bundle = route_authority_results(
            [case["result"]],
            domain="low_back_pain",
            risk_level="medium",
            population=case["population"],
            use_case=case["use_case"],
            now=NOW,
        )
        assert bundle.accepted == (), expected_reason
        assert bundle.rejections[0].reason == expected_reason


def test_public_manifest_exposes_trace_not_private_or_paid_body():
    bundle = route_authority_results(
        [_result()],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    public = bundle.public_manifest()
    assert public == {
        "status": "sufficient",
        "evidence_refs": [
            "claim:c_low_back_serious_cause_screening_boundary"
        ],
        "artifacts": [
            {
                "doc_id": (
                    "claim:c_low_back_serious_cause_screening_boundary"
                ),
                "sha256": (
                    "8e943e3a0caf2b2a903e0d3601c9b163"
                    "536d88d73e5d7c64d1a63382fb9a1730"
                ),
            }
        ],
        "sources": [
            {
                "source": "https://www.nice.org.uk/guidance/ng59",
                "kind": "guideline",
                "organization": "NICE",
                "title": "Low back pain and sciatica in over 16s: assessment and management",
                "version": "NG59 updated 2020-12-11",
                "authority_tier": "T1",
            }
        ],
    }
    serialized = str(public)
    assert "初次腰痛评估应先检查" not in serialized
    assert "paid_course_raw" not in serialized


def test_prompt_uses_short_reviewed_claim_and_source_id_only():
    bundle = route_authority_results(
        [_result()],
        domain="low_back_pain",
        risk_level="medium",
        population="adults_16_plus",
        use_case="initial_assessment",
        now=NOW,
    )

    prompt = bundle.to_prompt()
    assert "腰痛自我管理前先筛严重病因线索" in prompt
    assert "腰痛先筛重大外伤" in prompt
    assert "nice:ng59" in prompt
    assert "初次腰痛评估应先检查" not in prompt
