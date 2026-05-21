"""Deterministic verifier for user-visible health advice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


HIGH_RISK_DOMAINS = {"supplement", "medication", "doctor_handoff"}
LOW_RISK_DOMAINS = {"sleep", "movement", "recovery", "emotion", "metabolic", "measurement"}
GUIDELINE_SOURCE_TYPES = {"guideline", "cpic", "fda", "drug_label"}
PAID_CONTENT_LEAK_MARKERS = ("课程原文", "付费课程正文", "逐字稿", "原文如下")
EPIGENETIC_MARKERS = ("甲基化", "表观遗传", "epigenetic", "methylation", "生物年龄", "pace of aging")
EPIGENETIC_OVERCLAIM_MARKERS = (
    "证明",
    "逆转",
    "治愈",
    "抗衰成功",
    "真实衰老速度改变",
    "短期疗效",
    "7 天",
    "7天",
    "一周",
)


@dataclass(frozen=True)
class AdviceVerification:
    allowed: bool
    decision: str
    reason: str
    required_changes: list[str] = field(default_factory=list)
    audit_tags: list[str] = field(default_factory=list)


def verify_advice(
    candidate: Any,
    evidence_resolution: Any,
    personal_matrix: dict[str, Any] | None,
    contraindications: list[dict[str, Any]] | None,
) -> AdviceVerification:
    evidence_refs = _candidate_list(candidate, "evidence_refs") or _resolution_list(
        evidence_resolution, "evidence_refs"
    )
    source_types = {
        str(item).lower()
        for item in (
            _candidate_list(candidate, "evidence_source_types")
            or _resolution_list(evidence_resolution, "source_types")
        )
    }
    domain = str(getattr(candidate, "domain", "") or "").lower()

    if _looks_like_paid_content_leak(getattr(candidate, "body", "") or ""):
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="paid_content_leakage",
            required_changes=["remove_paid_source_excerpt"],
            audit_tags=["paid_content_leakage"],
        )

    if _is_epigenetic_overclaim(candidate, personal_matrix or {}):
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="epigenetic_overclaim",
            required_changes=["rewrite_as_long_term_proxy"],
            audit_tags=["epigenetic_boundary"],
        )

    contraindication = _matching_contraindication(candidate, contraindications or [])
    if contraindication is not None:
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="contraindicated",
            required_changes=["choose_fallback_protocol"],
            audit_tags=[contraindication.get("contraindication_id") or "contraindication"],
        )

    if _is_pgx_medication_advice(candidate, personal_matrix or {}) and not (
        source_types & GUIDELINE_SOURCE_TYPES
    ):
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="pgx_medication_requires_guideline",
            required_changes=["attach_guideline_or_cpic_source"],
            audit_tags=["pgx_medication_boundary"],
        )

    if _is_high_risk(candidate):
        required_changes = []
        if not evidence_refs:
            required_changes.append("evidence_refs")
        if not getattr(candidate, "verification_metric", None):
            required_changes.append("verification_metric")
        if required_changes:
            return AdviceVerification(
                allowed=False,
                decision="blocked",
                reason="high_risk_missing_evidence",
                required_changes=required_changes,
                audit_tags=["unsupported_high_risk_advice"],
            )

    if domain in LOW_RISK_DOMAINS and not evidence_refs and not source_types:
        return AdviceVerification(
            allowed=True,
            decision="downgraded",
            reason="low_risk_missing_external_evidence",
            required_changes=["mark_model_inference"],
            audit_tags=["model_inference"],
        )

    return AdviceVerification(allowed=True, decision="allowed", reason="allowed")


def _is_high_risk(candidate: Any) -> bool:
    domain = str(getattr(candidate, "domain", "") or "").lower()
    explicit_risk = str(getattr(candidate, "risk_level", "") or "").lower()
    text = f"{getattr(candidate, 'title', '')} {getattr(candidate, 'body', '')}".lower()
    return (
        domain in HIGH_RISK_DOMAINS
        or explicit_risk == "high"
        or "pgx" in text
        or "cyp2" in text
        or "用药" in text
    )


def _is_pgx_medication_advice(candidate: Any, personal_matrix: dict[str, Any]) -> bool:
    text = f"{getattr(candidate, 'title', '')} {getattr(candidate, 'body', '')}".lower()
    if "用药" in text or "药" in text or "medication" in text:
        if "pgx" in text or "cyp2" in text:
            return True
        for signal in personal_matrix.get("signals") or []:
            if isinstance(signal, dict) and str(signal.get("signal_type") or "").lower() == "genetics":
                return True
    return False


def _is_epigenetic_overclaim(candidate: Any, personal_matrix: dict[str, Any]) -> bool:
    text = f"{getattr(candidate, 'title', '')} {getattr(candidate, 'body', '')}".lower()
    has_epigenetic_text = any(marker.lower() in text for marker in EPIGENETIC_MARKERS)
    has_epigenetic_signal = any(
        isinstance(signal, dict)
        and str(signal.get("signal_type") or "").lower() == "epigenetic"
        for signal in personal_matrix.get("signals") or []
    )
    if not (has_epigenetic_text or has_epigenetic_signal):
        return False
    return any(marker.lower() in text for marker in EPIGENETIC_OVERCLAIM_MARKERS)


def _matching_contraindication(
    candidate: Any,
    contraindications: list[dict[str, Any]],
) -> dict[str, Any] | None:
    target = str(getattr(candidate, "target_value", "") or "").lower()
    title = str(getattr(candidate, "title", "") or "").lower()
    for contraindication in contraindications:
        blocks = {str(item).lower() for item in contraindication.get("blocks") or []}
        if target and target in blocks:
            return contraindication
        if "increase_intensity" in blocks and ("提高运动强度" in title or "高强度" in title):
            return contraindication
        if "protocol:movement:hiit" in blocks and ("hiit" in title or "高强度" in title):
            return contraindication
    return None


def _looks_like_paid_content_leak(text: str) -> bool:
    if any(marker in text for marker in PAID_CONTENT_LEAK_MARKERS):
        return True
    return text.count("得到") >= 20


def _candidate_list(candidate: Any, field_name: str) -> list[Any]:
    value = getattr(candidate, field_name, None)
    if not value:
        return []
    return list(value)


def _resolution_list(evidence_resolution: Any, field_name: str) -> list[Any]:
    if evidence_resolution is None:
        return []
    if isinstance(evidence_resolution, dict):
        value = evidence_resolution.get(field_name)
    else:
        value = getattr(evidence_resolution, field_name, None)
    if not value:
        return []
    return list(value)
