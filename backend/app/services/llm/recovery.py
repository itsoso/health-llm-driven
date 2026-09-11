"""LLM failure classification and one-hop recovery routing.

This layer only handles infrastructure failures such as quota/rate limit/timeouts.
It does not override health safety gates, tool validation, or write-intent review.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any, Optional

from app.config import settings
from app.services.llm.factory import create_provider_for_model_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMErrorDiagnosis:
    error_class: str
    recoverable: bool
    recommended_action: str
    execution_status: str = "failed"
    retry_at: Optional[str] = None


def _error_text(error: BaseException | str | None) -> str:
    return re.sub(r"\s+", " ", str(error or "")).strip().lower()


def diagnose_llm_error(error: BaseException | str | None) -> LLMErrorDiagnosis:
    """Classify provider errors into a small stable policy vocabulary."""
    # Policy errors are evaluated before transport status codes. In particular,
    # consent verification uses HTTP 503: changing providers cannot repair that
    # authorization boundary and must never trigger an external fallback call.
    if getattr(error, "error_code", None) == "llm_budget_exceeded":
        reason = getattr(error, "reason", None)
        unavailable = reason == "budget_guard_unavailable"
        return LLMErrorDiagnosis(
            "budget_guard_unavailable" if unavailable else "budget_exhausted",
            False,
            "retry_guard_later" if unavailable else "wait_budget_period",
            "blocked",
            getattr(error, "retry_at", None),
        )
    detail = getattr(error, "detail", None)
    policy_code = detail.get("code") if isinstance(detail, dict) else None
    policy_errors = {
        "ai_consent_required": ("consent_required", "request_consent"),
        "ai_consent_unavailable": ("consent_unavailable", "retry_consent_verification"),
        "ai_recipient_not_disclosed": ("recipient_not_disclosed", "surface_error"),
        "ai_consent_policy_changed": ("consent_required", "request_consent"),
        "auth_session_changed": ("auth_session_changed", "refresh_session"),
    }
    if policy_code in policy_errors:
        error_class, action = policy_errors[policy_code]
        return LLMErrorDiagnosis(error_class, False, action, "blocked")
    text = _error_text(error)
    if not text:
        return LLMErrorDiagnosis("unknown", False, "surface_error")
    if "monthly token quota" in text or "llm_budget_exceeded" in text:
        return LLMErrorDiagnosis("budget_exhausted", False, "alert_admin", "blocked")
    if "insufficient_quota" in text or "quota" in text or "token-plan quota" in text:
        return LLMErrorDiagnosis("quota_exhausted", True, "fallback_model")
    if "rate_limit" in text or "rate limit" in text or "429" in text:
        return LLMErrorDiagnosis("rate_limited", True, "fallback_model")
    if "timeout" in text or "timed out" in text or "read timed out" in text:
        return LLMErrorDiagnosis("timeout", True, "fallback_model")
    if "401" in text or "403" in text or "unauthorized" in text or "invalid api key" in text:
        return LLMErrorDiagnosis("auth_error", False, "alert_admin")
    if "500" in text or "502" in text or "503" in text or "504" in text or "service unavailable" in text:
        return LLMErrorDiagnosis("provider_error", True, "fallback_model")
    return LLMErrorDiagnosis("unknown", False, "surface_error")


def _env_available(model_id: str) -> bool:
    try:
        from app.services.llm.model_registry import get_model, _env_present

        entry = get_model(model_id)
        if not entry or not entry.chat_selectable:
            return False
        return all(_env_present(env, settings) for env in entry.requires_env)
    except Exception:
        logger.debug("[llm.recovery] model availability check failed", exc_info=True)
        return False


def pick_recovery_model_id(
    diagnosis: LLMErrorDiagnosis,
    *,
    primary_provider: Optional[str] = None,
    primary_model: Optional[str] = None,
) -> Optional[str]:
    """Pick an explicitly configured fallback model id."""
    configured = getattr(settings, "llm_recovery_model_id", None)
    if configured and _env_available(configured):
        return configured
    return None


async def try_recover_chat(
    error: BaseException,
    *,
    messages: list[dict[str, Any]],
    model: Optional[str],
    temperature: float,
    max_tokens: int,
    primary_provider: Optional[str],
    primary_model: Optional[str],
    kwargs: dict[str, Any],
    recovery_model_id: Optional[str] = None,
) -> tuple[bool, Optional[Any], Optional[str], LLMErrorDiagnosis]:
    """Try one fallback chat call. Returns (ok, result, recovery_model_id, diagnosis)."""
    diagnosis = diagnose_llm_error(error)
    if not getattr(settings, "llm_auto_recovery_enabled", False):
        return False, None, None, diagnosis
    if not diagnosis.recoverable:
        return False, None, None, diagnosis

    recovery_model_id = recovery_model_id or pick_recovery_model_id(
        diagnosis,
        primary_provider=primary_provider,
        primary_model=primary_model,
    )
    if not recovery_model_id:
        return False, None, None, diagnosis

    try:
        provider = create_provider_for_model_id(recovery_model_id)
        result = await provider.chat(
            messages,
            model=None,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **kwargs,
        )
        return True, result, recovery_model_id, diagnosis
    except Exception as fallback_error:  # noqa: BLE001
        fallback_diagnosis = diagnose_llm_error(fallback_error)
        logger.warning(
            "[llm.recovery] fallback failed primary=%s/%s recovery=%s error_type=%s error_class=%s",
            primary_provider,
            primary_model,
            recovery_model_id,
            type(fallback_error).__name__,
            fallback_diagnosis.error_class,
        )
        if fallback_diagnosis.execution_status == "blocked":
            # The primary transport failure is independently recorded by the
            # usage wrapper. Surface the final policy boundary to the caller.
            raise
        return False, None, recovery_model_id, fallback_diagnosis
