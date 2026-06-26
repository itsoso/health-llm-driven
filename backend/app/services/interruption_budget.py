"""Structured interruption-budget policy for proactive health nudges.

This module is intentionally pure so notification tasks, watch summaries, and
future surfaces can share the same P0/P1/P2 semantics without reimplementing
quiet-hours and budget explanations.
"""
from __future__ import annotations

from typing import Any


PROACTIVE_TIERS = ("P0", "P1", "P2")
REQUIRED_CONTRACT_FIELDS = ("reason", "action", "fallback_surface")


def normalize_tier(tier: str | None) -> str:
    text = str(tier or "P1").strip().upper()
    return text if text in PROACTIVE_TIERS else "P1"


def _missing_contract_fields(
    *,
    reason: str | None,
    action: str | None,
    fallback_surface: str | None,
) -> list[str]:
    values = {
        "reason": reason,
        "action": action,
        "fallback_surface": fallback_surface,
    }
    return [
        key
        for key in REQUIRED_CONTRACT_FIELDS
        if not str(values.get(key) or "").strip()
    ]


def evaluate_interruption(
    *,
    tier: str,
    sent_global: int,
    global_budget: int,
    sent_tier: int = 0,
    tier_budget: int | None = None,
    in_quiet_hours: bool = False,
    in_busy_window: bool = False,
    reason: str | None = None,
    action: str | None = None,
    fallback_surface: str | None = None,
) -> dict[str, Any]:
    """Return an explainable interruption decision.

    P0 is reserved for urgent/safety-critical notifications. It can bypass
    quiet hours but remains capped by the global and P0 tier budgets. P1 is
    actionable but must respect quiet hours and busy windows. P2 is log-only.
    Missing reason/action/fallback fields are reported for migration safety but
    do not block legacy callers yet.
    """
    normalized_tier = normalize_tier(tier)
    missing = _missing_contract_fields(
        reason=reason,
        action=action,
        fallback_surface=fallback_surface,
    )
    blocked_reason: str | None = None
    delivery_policy = "immediate"
    quiet_hours_respected = not in_quiet_hours

    if normalized_tier == "P2":
        blocked_reason = "log_only"
        delivery_policy = "log_only"
        quiet_hours_respected = True
    elif global_budget > 0 and sent_global >= global_budget:
        blocked_reason = "global_budget"
        delivery_policy = "suppress"
    elif normalized_tier == "P0":
        if tier_budget is not None and tier_budget > 0 and sent_tier >= tier_budget:
            blocked_reason = "tier_budget"
            delivery_policy = "suppress"
        elif in_quiet_hours:
            quiet_hours_respected = False
    elif in_quiet_hours:
        blocked_reason = "quiet_hours"
        delivery_policy = "delay_or_fallback"
        quiet_hours_respected = True
    elif in_busy_window:
        blocked_reason = "busy_window"
        delivery_policy = "delay_or_fallback"

    return {
        "allowed": blocked_reason is None,
        "tier": normalized_tier,
        "blocked_reason": blocked_reason,
        "delivery_policy": delivery_policy,
        "quiet_hours_respected": quiet_hours_respected,
        "busy_window_respected": not in_busy_window or blocked_reason == "busy_window",
        "contract_complete": not missing,
        "missing_contract_fields": missing,
        "contract": {
            "reason": reason,
            "action": action,
            "fallback_surface": fallback_surface,
        },
        "budget": {
            "sent_global": sent_global,
            "global_budget": global_budget,
            "sent_tier": sent_tier,
            "tier_budget": tier_budget,
        },
    }
