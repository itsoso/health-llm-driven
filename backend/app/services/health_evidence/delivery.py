"""Fail-closed delivery policy for persisted and shortcut health answers.

The health evidence runtime protects newly synthesized answers inside
``AgentExecutor``.  This module applies the same public manifest contract to
delivery paths that do not synthesize: history, durable replay, and API
shortcuts.  It never reconstructs private personal evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Any, Mapping

from .authority import is_current_health_evidence_artifact
from .continuation import parse_health_evidence_continuation
from .intent import classify_health_intent
from .verifier import health_answer_text_sha256, health_manifest_sha256


_CURRENT_MANIFEST_VERSION = "health-evidence.v1"
_CURRENT_INTENT_VERSION = "health-intent.v1"
_VERIFIER_VERDICTS = frozenset({"pass", "repair", "block"})
_SUFFICIENCY_VALUES = frozenset(
    {"sufficient", "clarify", "safe_fallback"}
)
_RISK_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "emergency": 3,
}
_CANONICAL_MANIFEST_KEYS = (
    "version",
    "intent",
    "risk_level",
    "sufficiency",
    "verifier_verdict",
    "context_categories_used",
    "personal_evidence_refs",
    "authority_evidence_refs",
    "authority_artifacts",
    "evidence_refs",
    "authority_sources",
    "sources",
    "missing_discriminators",
    "urgent_red_flags",
    "detected_red_flags",
    "safety_precautions",
    "gaps",
    "conflicts",
    "truncated",
    "limitations",
)


@dataclass(frozen=True)
class HealthDelivery:
    """One privacy-safe projection ready for an API response."""

    content: str
    meta: dict[str, Any]
    sanitized: bool


@dataclass(frozen=True)
class ProjectedHealthMessage:
    """One persisted message projected under the current release policy."""

    role: str
    content: str
    meta: dict[str, Any]
    sanitized: bool


def requires_live_health_executor(
    query: str,
    *,
    enabled: bool,
    extra_context: str | None = None,
) -> bool:
    """Return whether a pre-executor shortcut must be skipped."""

    if not enabled:
        return False
    if parse_health_evidence_continuation(extra_context).attempted:
        return True
    return classify_health_intent(query).requires_authority


def sanitize_health_delivery(
    *,
    source_query: str,
    assistant_content: str,
    assistant_meta: Any,
    enabled: bool,
    source_query_bound: bool = True,
) -> HealthDelivery:
    """Replace an unverified persisted health answer with a safe projection.

    ``source_query`` is the paired user message, not any private context packet.
    A current verified manifest keeps the original content byte-for-byte.  An
    old or malformed health row loses its body, evidence cards, and source labels.
    """

    content = str(assistant_content or "")
    meta = _verified_answer_evidence_meta(
        assistant_meta if isinstance(assistant_meta, Mapping) else {}
    )
    metadata_claims_health = _metadata_claims_health(meta)
    if not enabled and not metadata_claims_health:
        return HealthDelivery(content=content, meta=meta, sanitized=False)

    intent = classify_health_intent(source_query)
    if not intent.requires_authority and not metadata_claims_health:
        return HealthDelivery(content=content, meta=meta, sanitized=False)
    expected_intent_id = (
        intent.intent_id
        if intent.requires_authority
        else _claimed_health_intent_id(meta)
    )
    if (
        source_query_bound
        and expected_intent_id
        and has_current_health_verification(
            meta,
            intent_id=expected_intent_id,
            assistant_content=content,
            expected_risk_level=(
                intent.risk_level.value
                if intent.requires_authority
                else None
            ),
        )
    ):
        manifest = meta["health_evidence_manifest"]
        return HealthDelivery(
            content=content,
            meta=_canonical_verified_meta(meta, manifest),
            sanitized=False,
        )

    query_risk = (
        intent.risk_level.value
        if intent.requires_authority
        else None
    )
    claimed_risk = _max_known_risk(
        query_risk,
        _claimed_health_risk(meta),
    ) or "medium"
    meta = {
        "cards": [],
        "sources_used": [],
        "health_evidence_replay_sanitized": True,
    }
    return HealthDelivery(
        content=unverified_health_delivery_text(claimed_risk),
        meta=meta,
        sanitized=True,
    )


def project_persisted_health_messages(
    messages: Iterable[Mapping[str, Any] | object],
    *,
    initial_source_query: str | None = None,
) -> tuple[ProjectedHealthMessage, ...]:
    """Project persisted rows using one paired user→assistant policy.

    Mapping rows and ORM/object rows are both accepted.  A health-evidence
    assistant without a real preceding user row (or an explicitly supplied
    source query for a paginated window) is not source-bound and therefore
    fails closed.  Persisted projections always revalidate current artifacts,
    independently of the synthesis feature flag.
    """

    source_query = str(initial_source_query or "")
    source_bound = initial_source_query is not None
    projected: list[ProjectedHealthMessage] = []
    for message in messages:
        if isinstance(message, Mapping):
            role = str(message.get("role") or "")
            content = str(message.get("content") or "")
            raw_meta = message.get("meta")
        else:
            role = str(getattr(message, "role", "") or "")
            content = str(getattr(message, "content", "") or "")
            raw_meta = getattr(message, "meta", None)
        meta = dict(raw_meta) if isinstance(raw_meta, Mapping) else {}

        if role == "user":
            source_query = content
            source_bound = True
            projected.append(
                ProjectedHealthMessage(
                    role=role,
                    content=content,
                    meta=meta,
                    sanitized=False,
                )
            )
            continue
        if role != "assistant":
            projected.append(
                ProjectedHealthMessage(
                    role=role,
                    content=content,
                    meta=meta,
                    sanitized=False,
                )
            )
            continue

        delivery = sanitize_health_delivery(
            source_query=source_query,
            assistant_content=content,
            assistant_meta=meta,
            enabled=True,
            source_query_bound=source_bound,
        )
        projected.append(
            ProjectedHealthMessage(
                role=role,
                content=delivery.content,
                meta=delivery.meta,
                sanitized=delivery.sanitized,
            )
        )
    return tuple(projected)


def _metadata_claims_health(meta: Mapping[str, Any]) -> bool:
    if (
        "health_evidence_manifest" in meta
        or "health_evidence_verification" in meta
    ):
        return True
    cards = meta.get("cards")
    return bool(
        isinstance(cards, list)
        and any(
            isinstance(card, Mapping)
            and card.get("type") == "health_evidence"
            for card in cards
        )
    )


def metadata_claims_health(value: Any) -> bool:
    """Return whether a public payload carries health-evidence release metadata."""

    return (
        _metadata_claims_health(value)
        if isinstance(value, Mapping)
        else False
    )


def health_evidence_snapshot_meta(value: Any) -> dict[str, Any]:
    """Return the minimal private snapshot proof needed for later revalidation."""

    if not isinstance(value, Mapping):
        return {}
    return {
        key: deepcopy(value[key])
        for key in (
            "health_evidence_manifest",
            "health_evidence_verification",
        )
        if key in value
    }


def health_release_policy_fingerprint() -> str:
    """Hash the release inputs that govern persisted health verification."""

    from app.services.clinical_claim_release import (
        CLINICAL_RELEASE_HOLD_DOCUMENT_IDS,
        HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS,
        HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE,
    )

    from .authority import LOW_BACK_CLAIM_POLICY

    payload = {
        "version": "health-delivery-policy.v2",
        "manifest_version": _CURRENT_MANIFEST_VERSION,
        "intent_version": _CURRENT_INTENT_VERSION,
        "serving_scope": HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE,
        "held_document_ids": sorted(
            CLINICAL_RELEASE_HOLD_DOCUMENT_IDS
        ),
        "released_claim_ids": sorted(
            HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS
        ),
        "artifact_sha256": {
            doc_id: policy.artifact_sha256
            for doc_id, policy in sorted(LOW_BACK_CLAIM_POLICY.items())
        },
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _claimed_health_intent_id(meta: Mapping[str, Any]) -> str | None:
    manifest = meta.get("health_evidence_manifest")
    if not isinstance(manifest, Mapping):
        return None
    intent = manifest.get("intent")
    if not isinstance(intent, Mapping):
        return None
    intent_id = str(intent.get("intent_id") or "").strip()
    return intent_id if intent_id.startswith("health_advice.") else None


def _claimed_health_risk(meta: Mapping[str, Any]) -> str | None:
    manifest = meta.get("health_evidence_manifest")
    if not isinstance(manifest, Mapping):
        return None
    public_intent = manifest.get("intent")
    intent_risk = (
        public_intent.get("risk_level")
        if isinstance(public_intent, Mapping)
        else None
    )
    return _max_known_risk(
        manifest.get("risk_level"),
        intent_risk,
        default=None,
    )


def _max_known_risk(
    *values: Any,
    default: str | None = "medium",
) -> str | None:
    known = [
        normalized
        for value in values
        if (normalized := _known_risk(value)) is not None
    ]
    if not known:
        return default
    return max(known, key=_RISK_RANK.__getitem__)


def _known_risk(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in _RISK_RANK else None


def has_current_health_verification(
    value: Any,
    *,
    intent_id: str,
    assistant_content: str,
    expected_risk_level: str | None = None,
) -> bool:
    """Validate the manifest, treating expected risk as a minimum safety floor."""

    if not isinstance(value, Mapping):
        return False
    manifest = value.get("health_evidence_manifest")
    verification = value.get("health_evidence_verification")
    if not isinstance(manifest, Mapping) or not isinstance(
        verification,
        Mapping,
    ):
        return False

    public_intent = manifest.get("intent")
    if not isinstance(public_intent, Mapping):
        return False
    if manifest.get("version") != _CURRENT_MANIFEST_VERSION:
        return False
    if public_intent.get("version") != _CURRENT_INTENT_VERSION:
        return False
    if str(public_intent.get("intent_id") or "") != intent_id:
        return False
    if public_intent.get("requires_authority") is not True:
        return False

    raw_risk_level = manifest.get("risk_level")
    risk_level = _known_risk(raw_risk_level)
    if (
        risk_level is None
        or raw_risk_level != risk_level
        or public_intent.get("risk_level") != risk_level
    ):
        return False
    if expected_risk_level is not None:
        expected_risk = _known_risk(expected_risk_level)
        # A frozen Twin or Guardian signal may conservatively promote the
        # server-sealed turn above the risk visible in the paired user query.
        if (
            expected_risk is None
            or _RISK_RANK[risk_level] < _RISK_RANK[expected_risk]
        ):
            return False
    sufficiency = str(manifest.get("sufficiency") or "")
    if sufficiency not in _SUFFICIENCY_VALUES:
        return False

    verdict = str(verification.get("verdict") or "")
    if (
        verdict not in _VERIFIER_VERDICTS
        or manifest.get("verifier_verdict") != verdict
    ):
        return False
    if sufficiency == "clarify" and verdict != "repair":
        return False
    if sufficiency == "safe_fallback" and verdict != "block":
        return False
    if risk_level in {"high", "emergency"} and verdict != "block":
        return False

    manifest_hash = str(
        verification.get("manifest_sha256") or ""
    ).strip().lower()
    if len(manifest_hash) != 64 or not hmac.compare_digest(
        manifest_hash,
        health_manifest_sha256(manifest),
    ):
        return False

    released_hash = str(
        verification.get("released_text_sha256") or ""
    ).strip().lower()
    if len(released_hash) != 64 or not hmac.compare_digest(
        released_hash,
        health_answer_text_sha256(assistant_content),
    ):
        return False

    evidence_refs = manifest.get("evidence_refs")
    authority_refs = manifest.get("authority_evidence_refs")
    refs_used = verification.get("evidence_refs_used")
    normalized_evidence_refs = _unique_ref_list(evidence_refs)
    normalized_authority_refs = _unique_ref_list(authority_refs)
    normalized_refs_used = _unique_ref_list(refs_used)
    if (
        normalized_evidence_refs is None
        or normalized_authority_refs is None
        or normalized_refs_used is None
    ):
        return False
    if normalized_authority_refs != normalized_refs_used:
        return False
    if [
        ref
        for ref in normalized_evidence_refs
        if ref.startswith("claim:")
    ] != normalized_authority_refs:
        return False
    if (
        sufficiency == "sufficient"
        and verdict in {"pass", "repair"}
        and not normalized_refs_used
    ):
        return False

    authority_artifacts = manifest.get("authority_artifacts")
    if not isinstance(authority_artifacts, list):
        return False
    artifact_ids: list[str] = []
    artifact_by_id: dict[str, str] = {}
    for raw in authority_artifacts:
        if not isinstance(raw, Mapping):
            return False
        doc_id = str(raw.get("doc_id") or "").strip()
        sha256 = str(raw.get("sha256") or "").strip().lower()
        if not doc_id or doc_id in artifact_by_id:
            return False
        artifact_ids.append(doc_id)
        artifact_by_id[doc_id] = sha256
    if artifact_ids != normalized_refs_used:
        return False
    if not all(
        is_current_health_evidence_artifact(
            doc_id,
            artifact_by_id[doc_id],
        )
        for doc_id in normalized_refs_used
    ):
        return False
    return True


def _unique_ref_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    refs: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            return None
        ref = raw.strip()
        if not ref or ref != raw:
            return None
        refs.append(ref)
    if len(refs) != len(set(refs)):
        return None
    return refs


def _canonical_verified_meta(
    meta: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    canonical_manifest = {
        key: deepcopy(manifest[key])
        for key in _CANONICAL_MANIFEST_KEYS
        if key in manifest
    }
    verification = meta["health_evidence_verification"]
    canonical_verification = {
        "verdict": verification["verdict"],
        "evidence_refs_used": deepcopy(
            verification["evidence_refs_used"]
        ),
        "released_text_sha256": verification[
            "released_text_sha256"
        ],
        "manifest_sha256": health_manifest_sha256(
            canonical_manifest
        ),
    }
    canonical_meta: dict[str, Any] = {
        "health_evidence_manifest": canonical_manifest,
        "health_evidence_verification": canonical_verification,
    }
    verified_answer_meta = _verified_answer_evidence_meta(meta)
    if "answer_evidence" in verified_answer_meta:
        canonical_meta["answer_evidence"] = verified_answer_meta[
            "answer_evidence"
        ]
        canonical_meta["answer_evidence_sha256"] = verified_answer_meta[
            "answer_evidence_sha256"
        ]
    completion_status = meta.get("completion_status")
    if completion_status in {
        "complete",
        "interrupted",
        "failed",
        "error",
        "partial",
    }:
        canonical_meta["completion_status"] = completion_status
    if isinstance(meta.get("client_turn_finalized"), bool):
        canonical_meta["client_turn_finalized"] = meta[
            "client_turn_finalized"
        ]
    canonical_meta["cards"] = [
        {
            "type": "health_evidence",
            "data": canonical_manifest,
            "actions": [],
        }
    ]

    sources_used: list[str] = []
    for raw in canonical_manifest.get("authority_sources") or []:
        if not isinstance(raw, Mapping):
            continue
        organization = str(raw.get("organization") or "").strip()
        if organization and organization not in sources_used:
            sources_used.append(organization)
    context_categories = [
        str(item).strip()
        for item in canonical_manifest.get("context_categories_used") or []
        if str(item).strip()
    ]
    if context_categories:
        sources_used.append(
            "个人健康上下文：" + "、".join(context_categories)
        )
    canonical_meta["sources_used"] = sources_used
    canonical_meta["risk_level"] = str(
        canonical_manifest.get("risk_level") or ""
    )
    return canonical_meta


def _verified_answer_evidence_meta(meta: Mapping[str, Any]) -> dict[str, Any]:
    """Keep persisted answer evidence only when its canonical digest matches.

    This check intentionally runs before health-intent routing so ordinary tool
    answers and verified health answers have the same history integrity boundary.
    """

    from app.services.answer_evidence import (
        answer_evidence_sha256,
        normalize_answer_evidence,
    )

    output = dict(meta)
    answer_evidence = normalize_answer_evidence(output.get("answer_evidence"))
    expected_digest = output.get("answer_evidence_sha256")
    actual_digest = (
        answer_evidence_sha256(answer_evidence)
        if answer_evidence is not None
        else ""
    )
    if (
        answer_evidence is None
        or not isinstance(expected_digest, str)
        or len(expected_digest) != 64
        or not hmac.compare_digest(actual_digest, expected_digest)
    ):
        output.pop("answer_evidence", None)
        output.pop("answer_evidence_sha256", None)
        return output
    output["answer_evidence"] = answer_evidence
    output["answer_evidence_sha256"] = expected_digest
    return output


def unverified_health_delivery_text(risk_level: str) -> str:
    """Return a deterministic replacement without personal or paid content."""

    if risk_level == "emergency":
        return (
            "这条旧版本健康回答未经过当前健康安全校验，因此不再原样展示。"
            "你描述的情况可能包含需要立即处理的急症警示征象，"
            "请现在前往急诊或联系当地急救服务。这是安全分流，不是诊断。"
        )
    if risk_level == "high":
        return (
            "这条旧版本健康回答未经过当前健康安全校验，因此不再原样展示。"
            "本轮包含需要尽快就医评估的警示线索；如有严重外伤、高热、"
            "严重感染或症状快速加重，请现在前往急诊。这是安全分流，不是诊断。"
        )
    return (
        "这条旧版本健康回答未经过当前健康安全校验，因此不再原样展示。"
        "请重新发送健康问题，以便按当前个人上下文和权威证据重新分析。"
        "如有排尿困难、大小便失控、会阴或肛周麻木、双腿明显无力，"
        "请立即前往急诊。"
    )
