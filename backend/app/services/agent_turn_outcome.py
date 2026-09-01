"""Classify one Agent turn for honest UI state and privacy-safe telemetry.

This module deliberately consumes execution facts rather than model prose.  A
tool block, a tool error, a confirmation gate, and a model refusal are
different product states and must not collapse into one generic "拒绝回答".
"""
from __future__ import annotations

from typing import Any, Iterable


_REFUSAL_MARKERS = (
    "抱歉",
    "很抱歉",
    "无法提供",
    "不能提供",
    "无法回答",
    "不能回答",
    "无法帮助",
    "不能帮助",
    "只能记录",
    "只能查询",
)
_SAFETY_BOUNDARY_MARKERS = (
    "医疗判断",
    "安全边界",
    "诊断",
    "处方",
    "停药",
    "医生",
)
_ACTIONABLE_MARKERS = (
    "建议",
    "可以帮你",
    "如果",
    "请观察",
    "就医",
    "需要注意",
    "下一步",
)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _refusal_reason(text: str) -> str | None:
    """Return a coarse refusal code only for refusal-shaped short answers.

    A normal safety disclaimer often contains words such as "诊断" or "医生"
    but also gives useful next steps.  Those answers are intentionally excluded
    from refusal metrics.
    """
    normalized = " ".join(str(text or "").split())
    if not normalized or len(normalized) > 600:
        return None
    if not any(marker in normalized[:180] for marker in _REFUSAL_MARKERS):
        return None
    if any(marker in normalized for marker in _ACTIONABLE_MARKERS) and len(normalized) >= 80:
        return None
    if any(marker in normalized for marker in _SAFETY_BOUNDARY_MARKERS):
        return "safety_boundary"
    return "model_scope"


_ACTION_STATUSES = frozenset(
    {"verified", "rejected", "failed", "reconciliation_required", "waiting_for_user"}
)


def _public_action_outcomes(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a bounded, stack-trace-free per-action projection."""
    actions: list[dict[str, Any]] = []
    for raw in values or ():
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "").strip()
        if status not in _ACTION_STATUSES:
            continue
        action: dict[str, Any] = {"status": status}
        for key in ("action_id", "reason_code", "recovery_guidance"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                action[key] = value.strip()[:240]
        for key in ("dispatch_started", "receipt_verified"):
            if isinstance(raw.get(key), bool):
                action[key] = raw[key]
        actions.append(action)
        if len(actions) >= 32:
            break
    return actions


def classify_agent_turn_outcome(
    *,
    completion_status: str,
    final_text: str,
    capability_block_reasons: Iterable[str] = (),
    tool_failure_tools: Iterable[str] = (),
    pending_confirmation_tools: Iterable[str] = (),
    write_receipts: Iterable[dict[str, Any]] = (),
    record_intent_no_tool: bool = False,
    destructive_or_sync_no_tool: bool = False,
    write_reconciliation_required: bool = False,
    runtime_control_unavailable: bool = False,
    dispatch_started: bool = False,
    claimed_write_action_count: int = 0,
    action_outcomes: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Return a stable, content-free outcome payload for ``done.meta``.

    The precedence follows the user's recoverability path: confirmation is an
    intentional pause; policy blocks and tool failures are execution issues;
    only then do we classify the final model text as a refusal.
    """
    blocks = _unique(capability_block_reasons)
    failures = _unique(tool_failure_tools)
    confirmations = _unique(pending_confirmation_tools)
    receipts = tuple(write_receipts or ())
    verified_receipt_count = sum(
        1
        for receipt in receipts
        if isinstance(receipt, dict) and receipt.get("verified") is True
    )
    actions = _public_action_outcomes(action_outcomes)

    def outcome(
        *,
        status: str,
        category: str,
        reason_code: str,
        retryable: bool,
        refusal_detected: bool = False,
        confirmation_required: bool = False,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "category": category,
            "reason_code": reason_code,
            "retryable": retryable,
            "dispatch_started": bool(dispatch_started),
            "verified_receipt_count": verified_receipt_count,
            "actions": actions,
            "refusal_detected": refusal_detected,
            "capability_block_count": len(blocks),
            "tool_failure_count": len(failures),
            "confirmation_required": confirmation_required,
        }

    missing_claimed_receipt = (
        max(0, int(claimed_write_action_count or 0)) > verified_receipt_count
    )
    if write_reconciliation_required or missing_claimed_receipt or (dispatch_started and failures):
        return outcome(
            status="reconciliation_required",
            category="write_reconciliation_required",
            reason_code="missing_receipt",
            retryable=False,
        )
    if runtime_control_unavailable:
        return outcome(
            status="failed",
            category="service_unavailable",
            reason_code="runtime_control_unavailable",
            retryable=False,
        )
    if confirmations:
        return outcome(
            status="waiting_for_user",
            category="confirmation_required",
            reason_code=confirmations[0],
            retryable=False,
            confirmation_required=True,
        )
    if blocks:
        return outcome(
            status="blocked",
            category="tool_blocked",
            reason_code=blocks[0],
            retryable=False,
        )
    if failures:
        return outcome(
            status="failed",
            category="tool_failed",
            reason_code=failures[0],
            retryable=True,
        )
    if record_intent_no_tool or destructive_or_sync_no_tool:
        reason = "write_without_tool" if record_intent_no_tool else "mutation_without_tool"
        return outcome(
            status="failed",
            category="action_not_executed",
            reason_code=reason,
            retryable=True,
        )

    if completion_status != "complete":
        reason = "completion_error" if completion_status == "error" else "completion_interrupted"
        return outcome(
            status="failed",
            category="execution_error",
            reason_code=reason,
            retryable=True,
        )
    refusal_reason = _refusal_reason(final_text)
    if refusal_reason:
        return outcome(
            status="refused",
            category=(
                "safety_refusal" if refusal_reason == "safety_boundary" else "model_refusal"
            ),
            reason_code=refusal_reason,
            retryable=refusal_reason == "model_scope",
            refusal_detected=True,
        )
    if not str(final_text or "").strip():
        return outcome(
            status="failed",
            category="no_answer",
            reason_code="empty_final_text",
            retryable=True,
        )

    return outcome(
        status="complete",
        category="success",
        reason_code="verified_write" if verified_receipt_count else "completed",
        retryable=False,
    )
