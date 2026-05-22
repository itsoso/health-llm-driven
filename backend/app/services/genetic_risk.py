"""Risk display helpers for consumer genetic screening results."""

from __future__ import annotations

from typing import Any, Mapping, Optional


CONFIRMATION_EVIDENCE_LEVELS = {"requires_confirmation"}


def confirmation_required(
    evidence_level: Optional[str],
    health_implications: Optional[Mapping[str, Any]],
) -> bool:
    """Return whether a variant is only a screening hit pending clinical confirmation."""
    if (evidence_level or "").lower() in CONFIRMATION_EVIDENCE_LEVELS:
        return True
    if isinstance(health_implications, Mapping):
        return bool(health_implications.get("confirmation_required"))
    return False


def effective_risk_level(
    risk_level: Optional[str],
    category: Optional[str],
    evidence_level: Optional[str],
    health_implications: Optional[Mapping[str, Any]],
) -> str:
    """Risk level safe for user-facing disease ordering and counts.

    Monogenic/rare-disease DTC hits marked requires_confirmation should not be
    shown as confirmed high disease risk. Drug-safety hits keep their warning
    level because the actionable behavior is to confirm before using that drug.
    """
    raw = (risk_level or "info").lower()
    cat = (category or "").lower()
    if cat == "disease_risk" and confirmation_required(evidence_level, health_implications):
        return "info"
    return raw


def clinical_status(
    category: Optional[str],
    evidence_level: Optional[str],
    health_implications: Optional[Mapping[str, Any]],
) -> str:
    if confirmation_required(evidence_level, health_implications):
        return "requires_confirmation"
    if (category or "").lower() == "drug_sensitivity":
        return "pharmacogenomic_screening"
    return "screening"
