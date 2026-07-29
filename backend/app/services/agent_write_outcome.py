"""Structured write execution outcomes used by the Agent write safety gate.

Tool responses are still strings at the executor boundary for compatibility,
but their state must not be inferred from user-facing prose. This module
normalizes structured JSON responses first and keeps the legacy text fallback
only for older tools that have not migrated yet.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Literal


WriteExecutionStatus = Literal["verified", "rejected", "failed", "uncertain"]


@dataclass(frozen=True)
class WriteExecutionOutcome:
    status: WriteExecutionStatus
    error_code: str | None = None
    dispatch_started: bool | None = None
    receipt: dict[str, Any] | None = None


_REJECTED_STATUSES = {
    "rejected",
    "denied",
    "not_found",
    "cancelled",
    "canceled",
}
_FAILED_STATUSES = {"failed", "needs_confirmation", "confirmation_required"}
_UNCERTAIN_STATUSES = {
    "uncertain",
    "in_flight",
    "pending",
    "processing",
    "queued",
    "executing",
    "running",
    "retrying",
    "reconciliation_required",
    "partial",
    "timeout",
    "timed_out",
}
_COMPLETED_STATUSES = {
    "verified",
    "success",
    "completed",
    "recorded",
    "created",
    "updated",
    "deleted",
    "saved",
    "done",
    "taken",
    "skipped",
    "dismissed",
    "resolved",
    "active",
    "paused",
    "scheduled",
    "accepted",
    "placed",
    "sent",
    "executed",
    "ok",
}
_LOCAL_VALIDATION_MARKERS = (
    "参数解析失败",
    "只读预生成回合不执行写入/变更操作",
    "工具调用策略检查失败",
    "工具调用被策略拦截",
    "已阻止自动写入",
    "已阻止执行",
    "不是明确的本人症状记录请求",
    "不是明确的本人鼻炎症状记录请求",
    "带附件的症状内容暂不自动写入",
    "带附件的鼻炎症状暂不自动写入",
    "症状记录参数无效，已阻止",
    "鼻炎打卡参数无效，已阻止",
    "用药确认计划未能建立，本次没有写入",
    "必须提供",
    "需要提供",
    "缺少",
    "不支持",
)
_LOCAL_WRITE_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def local_write_rejection(
    error_code: str,
    *,
    message: str | None = None,
    recovery_guidance: str | None = None,
) -> str:
    """Build a deterministic pre-dispatch write rejection.

    Registered write adapters use this instead of natural-language ``Error:``
    strings. Runtime can then distinguish a safe local rejection from an
    external write whose outcome is unknown.
    """
    normalized_code = str(error_code or "").strip()
    if not _LOCAL_WRITE_ERROR_CODE_PATTERN.fullmatch(normalized_code):
        raise ValueError("invalid_local_write_error_code")
    payload: dict[str, Any] = {
        "status": "rejected",
        "success": False,
        "dispatch_started": False,
        "error_code": normalized_code,
    }
    if message:
        payload["message"] = str(message)
    if recovery_guidance:
        payload["recovery_guidance"] = str(recovery_guidance)
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def is_legacy_local_write_rejection(result: Any) -> bool:
    """Return whether a write still depends on the deprecated prose fallback."""
    if _structured_payload(result) is not None:
        return False
    text = str(result or "").strip()
    if text.startswith("Error: API 返回 "):
        return False
    return text.startswith("Error:") and any(
        marker in text for marker in _LOCAL_VALIDATION_MARKERS
    )


def _structured_payload(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return None
    text = result.strip()
    if not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _dispatch_started(payload: dict[str, Any]) -> bool | None:
    value = payload.get("dispatch_started")
    return value if isinstance(value, bool) else None


def classify_write_execution(
    result: Any,
    *,
    receipt: dict[str, Any] | None = None,
) -> WriteExecutionOutcome:
    """Classify one write using execution facts, not response prose.

    A receipt is the only verified-success signal. An explicit structured
    rejection is terminal and safe to continue from. A failed/uncertain result
    without a receipt remains non-successful, with uncertainty preserved when
    the tool says dispatch may have started.
    """
    if receipt:
        return WriteExecutionOutcome(
            status="verified",
            dispatch_started=True,
            receipt=receipt,
        )

    payload = _structured_payload(result)
    if payload is not None:
        status = str(payload.get("status") or "").strip().lower()
        error_code = str(payload.get("error_code") or "").strip() or None
        dispatch_started = _dispatch_started(payload)
        if status in _REJECTED_STATUSES:
            return WriteExecutionOutcome(
                status="rejected" if dispatch_started is False else "uncertain",
                error_code=error_code or status,
                dispatch_started=dispatch_started,
            )
        if status in _FAILED_STATUSES:
            return WriteExecutionOutcome(
                status="failed" if dispatch_started is False else "uncertain",
                error_code=error_code or status,
                dispatch_started=dispatch_started,
            )
        if status in _UNCERTAIN_STATUSES:
            return WriteExecutionOutcome(
                status="uncertain",
                error_code=error_code or status,
                dispatch_started=dispatch_started,
            )
        if status in _COMPLETED_STATUSES:
            return WriteExecutionOutcome(
                status="uncertain",
                error_code="missing_receipt",
                dispatch_started=dispatch_started,
            )
        if payload.get("success") is False or payload.get("ok") is False:
            return WriteExecutionOutcome(
                status="rejected" if dispatch_started is False else "uncertain",
                error_code=error_code or "write_failed",
                dispatch_started=dispatch_started,
            )

    text = str(result or "").strip()
    if text.startswith("[NEEDS_CLARIFICATION]"):
        return WriteExecutionOutcome(
            status="rejected",
            error_code="policy_blocked",
            dispatch_started=False,
        )
    if text.startswith("[NEEDS_CONFIRMATION]"):
        return WriteExecutionOutcome(status="failed", dispatch_started=False)
    # _api_post/_patch/_put/_delete prefix every HTTP failure with this marker
    # and include the upstream body verbatim. That body may coincidentally
    # contain a local-policy phrase such as “已阻止执行”; once an HTTP request
    # has crossed the boundary, keep the state uncertain rather than claiming
    # it was never dispatched.
    if text.startswith("Error: API 返回 "):
        return WriteExecutionOutcome(status="uncertain")
    if is_legacy_local_write_rejection(result):
        return WriteExecutionOutcome(status="rejected", dispatch_started=False)
    return WriteExecutionOutcome(status="uncertain")


def classify_explicit_write_execution(
    result: Any,
) -> WriteExecutionOutcome | None:
    """Classify only payloads that explicitly declare execution state.

    Legacy success payloads such as ``{"id": 42}`` carry a resource identity
    but no state marker. Callers that can build a receipt should use
    ``classify_write_execution(..., receipt=...)`` for those. This helper is
    for shared fail-closed handling without misclassifying legacy success JSON.
    """
    payload = _structured_payload(result)
    if payload is None:
        return None
    status = str(payload.get("status") or "").strip().lower()
    has_explicit_failure = payload.get("success") is False or payload.get("ok") is False
    if not status and not has_explicit_failure:
        return None
    return classify_write_execution(payload)


def result_declares_explicit_failure(result: Any) -> bool:
    """Return whether a result declares a hard failure for any tool kind.

    This intentionally excludes nonterminal business states such as
    ``pending`` and ``processing``. Write-specific callers still use
    ``classify_write_execution`` to fail closed when a verified receipt is
    missing; generic telemetry must not turn a valid read or a confirmed
    persisted draft into a tool failure.
    """
    payload = _structured_payload(result)
    if payload is None:
        return False
    if payload.get("success") is False or payload.get("ok") is False:
        return True
    error = payload.get("error")
    if error not in (None, "", False, {}, []):
        return True
    status = str(payload.get("status") or "").strip().lower()
    return status in {
        *_REJECTED_STATUSES,
        *_FAILED_STATUSES,
        "failed",
        "error",
        "failure",
    }


def write_result_declares_non_success(
    result: Any,
    *,
    allow_pending: bool = False,
    allowed_statuses: Collection[str] = (),
) -> bool:
    """Return whether a structured result explicitly forbids a success receipt.

    Resource identity proves which object a tool refers to, not that its
    mutation reached a terminal success state. Receipt builders and direct
    voice shortcuts share this gate so transitional or failed payloads cannot
    be promoted merely because they also contain an ID.
    """
    payload = _structured_payload(result)
    if payload is None:
        return False

    if payload.get("success") is False or payload.get("ok") is False:
        return True
    error = payload.get("error")
    if error not in (None, "", False, {}, []):
        return True

    status = str(payload.get("status") or "").strip().lower()
    if status == "pending" and allow_pending:
        return False
    if status in allowed_statuses:
        return False
    if status and status not in _COMPLETED_STATUSES:
        return True
    return False
