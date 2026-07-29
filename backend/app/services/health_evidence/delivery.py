"""Fail-closed delivery policy for persisted and shortcut health answers.

The health evidence runtime protects newly synthesized answers inside
``AgentExecutor``.  This module applies the same public manifest contract to
delivery paths that do not synthesize: history, durable replay, and API
shortcuts.  It never reconstructs private personal evidence.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hmac
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
_UNVERIFIED_META_KEYS = (
    "cards",
    "health_evidence_manifest",
    "health_evidence_verification",
    "risk_level",
    "sources_used",
)


@dataclass(frozen=True)
class HealthDelivery:
    """One privacy-safe projection ready for an API response."""

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
) -> HealthDelivery:
    """Replace an unverified persisted health answer with a safe projection.

    ``source_query`` is the paired user message, not any private context packet.
    A current verified manifest keeps the original content byte-for-byte.  An
    old or malformed health row loses its body, evidence cards, and source labels.
    """

    content = str(assistant_content or "")
    meta = dict(assistant_meta) if isinstance(assistant_meta, Mapping) else {}
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
    if expected_intent_id and has_current_health_verification(
        meta,
        intent_id=expected_intent_id,
        assistant_content=content,
        expected_risk_level=(
            intent.risk_level.value
            if intent.requires_authority
            else None
        ),
    ):
        manifest = meta["health_evidence_manifest"]
        return HealthDelivery(
            content=content,
            meta=_canonical_verified_meta(meta, manifest),
            sanitized=False,
        )

    claimed_risk = (
        intent.risk_level.value
        if intent.requires_authority
        else _claimed_health_risk(meta)
    )
    for key in _UNVERIFIED_META_KEYS:
        meta.pop(key, None)
    meta.update(
        {
            "cards": [],
            "sources_used": [],
            "health_evidence_replay_sanitized": True,
        }
    )
    return HealthDelivery(
        content=unverified_health_delivery_text(claimed_risk),
        meta=meta,
        sanitized=True,
    )


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


def _claimed_health_intent_id(meta: Mapping[str, Any]) -> str | None:
    manifest = meta.get("health_evidence_manifest")
    if not isinstance(manifest, Mapping):
        return None
    intent = manifest.get("intent")
    if not isinstance(intent, Mapping):
        return None
    intent_id = str(intent.get("intent_id") or "").strip()
    return intent_id if intent_id.startswith("health_advice.") else None


def _claimed_health_risk(meta: Mapping[str, Any]) -> str:
    manifest = meta.get("health_evidence_manifest")
    if not isinstance(manifest, Mapping):
        return "medium"
    public_intent = manifest.get("intent")
    risk_level = str(manifest.get("risk_level") or "").strip().lower()
    if not risk_level and isinstance(public_intent, Mapping):
        risk_level = str(
            public_intent.get("risk_level") or ""
        ).strip().lower()
    return risk_level if risk_level in {"emergency", "high"} else "medium"


def has_current_health_verification(
    value: Any,
    *,
    intent_id: str,
    assistant_content: str,
    expected_risk_level: str | None = None,
) -> bool:
    """Validate the current public manifest/verification delivery contract."""

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

    risk_level = str(manifest.get("risk_level") or "")
    if not risk_level or public_intent.get("risk_level") != risk_level:
        return False
    if (
        expected_risk_level is not None
        and risk_level != expected_risk_level
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
    canonical_meta = deepcopy(dict(meta))
    canonical_manifest = deepcopy(dict(manifest))
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
