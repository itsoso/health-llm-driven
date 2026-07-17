"""Release-readiness snapshot for operators and preflight checks.

This is deliberately separate from ``/health``: a running process is not the
same thing as a safe, observable, budgeted App Store candidate.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.sentry_status import sentry_status_snapshot


def _check(status: str, *, blocking: bool, reason: str) -> dict[str, Any]:
    return {"status": status, "blocking": blocking, "reason": reason}


def release_readiness_snapshot() -> dict[str, Any]:
    """Return a secret-free, deterministic release readiness report."""
    production = (settings.app_env or "").strip().lower() == "production"
    sentry = sentry_status_snapshot()
    checks: dict[str, dict[str, Any]] = {
        "production_debug": _check(
            "pass" if not (production and settings.debug) else "fail",
            blocking=True,
            reason="debug_disabled" if not (production and settings.debug) else "DEBUG must be false in production",
        ),
        "llm_recovery_bounded": _check(
            "pass"
            if not settings.llm_auto_recovery_enabled or bool((settings.llm_recovery_model_id or "").strip())
            else "fail",
            blocking=True,
            reason=(
                "disabled_by_default_or_explicit_model"
                if not settings.llm_auto_recovery_enabled or bool((settings.llm_recovery_model_id or "").strip())
                else "enabled_without_explicit_recovery_model"
            ),
        ),
        "tokenplan_budget": _check(
            "pass"
            if settings.llm_provider != "tokenplan" or int(settings.tokenplan_monthly_token_quota or 0) > 0
            else "fail",
            blocking=True,
            reason=(
                "not_using_tokenplan_or_explicit_monthly_quota"
                if settings.llm_provider != "tokenplan" or int(settings.tokenplan_monthly_token_quota or 0) > 0
                else "TOKENPLAN_MONTHLY_TOKEN_QUOTA is missing_or_zero"
            ),
        ),
        "sentry": _check(
            "pass" if sentry.get("enabled") else "fail",
            blocking=production,
            reason="configured" if sentry.get("enabled") else "SENTRY_DSN is not configured",
        ),
        "notification_pipeline": _check(
            "pass",
            blocking=True,
            reason="open_loop uses PushService for quiet-hours, dedup, gatekeeper and delivery logs",
        ),
        # These are intentionally manual until a production deletion drill and
        # final physical-device run have evidence attached to the dossier.
        "account_deletion_drill": _check(
            "manual",
            blocking=True,
            reason="production deletion scope and backup-retention drill required",
        ),
        "physical_iphone_gate": _check(
            "manual",
            blocking=True,
            reason="final RC must be verified on a real iPhone",
        ),
        "app_store_connect_privacy": _check(
            "manual",
            blocking=True,
            reason="App Privacy and regulated-medical-device declarations are App Store Connect steps",
        ),
    }
    blocking = [name for name, value in checks.items() if value["blocking"] and value["status"] != "pass"]
    return {
        "status": "ready" if not blocking else "blocked",
        "ready_for_backend_release": not any(
            value["blocking"] and value["status"] == "fail" for value in checks.values()
        ),
        "ready_for_app_store": not blocking,
        "production": production,
        "checks": checks,
        "blocking_checks": blocking,
    }
