"""Risk monotonicity at the persisted health-delivery boundary."""

from __future__ import annotations

from typing import Any

import pytest

import app.services.clinical_claim_release as release_policy
from app.services.health_evidence.authority import LOW_BACK_CLAIM_POLICY
from app.services.health_evidence.delivery import (
    project_persisted_health_messages,
    sanitize_health_delivery,
)
from app.services.health_evidence.verifier import (
    health_answer_text_sha256,
    health_manifest_sha256,
)


_MEDIUM_QUERY = "我腰疼怎么办"
_EMERGENCY_QUERY = "腰痛而且排不出尿"
_CONTENT = "server-sealed health response"


def _sealed_meta(
    risk_level: Any,
    *,
    claim_id: str | None = None,
) -> dict:
    authority_refs = [claim_id] if claim_id else []
    authority_artifacts = (
        [
            {
                "doc_id": claim_id,
                "sha256": LOW_BACK_CLAIM_POLICY[claim_id].artifact_sha256,
            }
        ]
        if claim_id
        else []
    )
    manifest = {
        "version": "health-evidence.v1",
        "intent": {
            "version": "health-intent.v1",
            "intent_id": "health_advice.symptom.low_back_pain",
            "intent": "health_advice",
            "domain": "low_back_pain",
            "risk_level": risk_level,
            "requires_authority": True,
        },
        "risk_level": risk_level,
        "sufficiency": "safe_fallback",
        "verifier_verdict": "block",
        "context_categories_used": ["symptom"],
        "personal_evidence_refs": ["personal:symptom:1"],
        "evidence_refs": [
            "personal:symptom:1",
            *authority_refs,
        ],
        "authority_evidence_refs": authority_refs,
        "authority_artifacts": authority_artifacts,
    }
    return {
        "health_evidence_manifest": manifest,
        "health_evidence_verification": {
            "verdict": "block",
            "evidence_refs_used": authority_refs,
            "released_text_sha256": health_answer_text_sha256(_CONTENT),
            "manifest_sha256": health_manifest_sha256(manifest),
        },
        "cards": [
            {
                "type": "health_evidence",
                "data": manifest,
                "actions": [],
            }
        ],
    }


def _rebind_manifest(meta: dict) -> None:
    manifest = meta["health_evidence_manifest"]
    meta["health_evidence_verification"]["manifest_sha256"] = (
        health_manifest_sha256(manifest)
    )


@pytest.mark.parametrize("promoted_risk", ["high", "emergency"])
def test_sealed_risk_above_query_floor_survives_sanitize(
    promoted_risk: str,
) -> None:
    delivery = sanitize_health_delivery(
        source_query=_MEDIUM_QUERY,
        assistant_content=_CONTENT,
        assistant_meta=_sealed_meta(promoted_risk),
        enabled=False,
    )

    assert delivery.sanitized is False
    assert delivery.content == _CONTENT
    assert delivery.meta["risk_level"] == promoted_risk


def test_sealed_emergency_risk_survives_persisted_projection() -> None:
    projection = project_persisted_health_messages(
        (
            {"role": "user", "content": _MEDIUM_QUERY, "meta": {}},
            {
                "role": "assistant",
                "content": _CONTENT,
                "meta": _sealed_meta("emergency"),
            },
        )
    )[-1]

    assert projection.sanitized is False
    assert projection.content == _CONTENT
    assert projection.meta["risk_level"] == "emergency"


def test_manifest_below_query_risk_floor_is_sanitized() -> None:
    delivery = sanitize_health_delivery(
        source_query=_EMERGENCY_QUERY,
        assistant_content=_CONTENT,
        assistant_meta=_sealed_meta("medium"),
        enabled=False,
    )

    assert delivery.sanitized is True
    assert delivery.content != _CONTENT
    assert "联系当地急救服务" in delivery.content


def test_unknown_manifest_risk_fails_closed_without_escalating_copy() -> None:
    delivery = sanitize_health_delivery(
        source_query=_MEDIUM_QUERY,
        assistant_content=_CONTENT,
        assistant_meta=_sealed_meta("critical"),
        enabled=False,
    )

    assert delivery.sanitized is True
    assert delivery.content != _CONTENT
    assert "请重新发送健康问题" in delivery.content
    assert "你描述的情况可能包含" not in delivery.content


@pytest.mark.parametrize("unknown_risk", [["emergency"], {"level": "emergency"}])
def test_non_scalar_manifest_risk_fails_closed(unknown_risk: Any) -> None:
    delivery = sanitize_health_delivery(
        source_query=_MEDIUM_QUERY,
        assistant_content=_CONTENT,
        assistant_meta=_sealed_meta(unknown_risk),
        enabled=False,
    )

    assert delivery.sanitized is True
    assert delivery.content != _CONTENT
    assert "请重新发送健康问题" in delivery.content


@pytest.mark.parametrize(
    ("declared_risk", "expected_text"),
    [
        ("high", "需要尽快就医评估"),
        ("emergency", "联系当地急救服务"),
    ],
)
def test_revoked_answer_fallback_keeps_higher_known_declared_risk(
    declared_risk: str,
    expected_text: str,
) -> None:
    meta = _sealed_meta(declared_risk)
    meta["health_evidence_manifest"]["limitations"] = ["tampered"]

    delivery = sanitize_health_delivery(
        source_query=_MEDIUM_QUERY,
        assistant_content=_CONTENT,
        assistant_meta=meta,
        enabled=False,
    )

    assert delivery.sanitized is True
    assert delivery.content != _CONTENT
    assert expected_text in delivery.content


def test_artifact_mismatch_still_revokes_promoted_answer() -> None:
    claim_id = "claim:c_low_back_serious_cause_screening_boundary"
    meta = _sealed_meta("high", claim_id=claim_id)
    meta["health_evidence_manifest"]["authority_artifacts"][0][
        "sha256"
    ] = "0" * 64
    _rebind_manifest(meta)

    delivery = sanitize_health_delivery(
        source_query=_MEDIUM_QUERY,
        assistant_content=_CONTENT,
        assistant_meta=meta,
        enabled=False,
    )

    assert delivery.sanitized is True
    assert delivery.content != _CONTENT
    assert "需要尽快就医评估" in delivery.content


def test_runtime_rehold_still_revokes_promoted_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim_id = "claim:c_low_back_serious_cause_screening_boundary"
    meta = _sealed_meta("high", claim_id=claim_id)
    monkeypatch.setattr(
        release_policy,
        "HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS",
        frozenset(),
    )

    delivery = sanitize_health_delivery(
        source_query=_MEDIUM_QUERY,
        assistant_content=_CONTENT,
        assistant_meta=meta,
        enabled=False,
    )

    assert delivery.sanitized is True
    assert delivery.content != _CONTENT
    assert "需要尽快就医评估" in delivery.content
