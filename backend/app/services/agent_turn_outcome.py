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


def agent_completion_metadata(
    generation_status: str, turn_outcome: dict[str, Any],
) -> dict[str, str]:
    """Keep transport diagnostics while old clients fail closed on task failure.

    ``turn_outcome`` is authoritative, including intentional confirmation pauses
    and partial results. ``generation_status`` retains the model finish state;
    the legacy completion enum stays compatible with deployed clients.
    """
    completion = generation_status
    if generation_status == "complete" and turn_outcome.get("status") in {
        "partial", "failed", "blocked", "refused", "reconciliation_required",
    }:
        completion = "error"
    return {"generation_status": generation_status, "completion_status": completion}


def _goal_evidence_outcomes(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project executor-verified postconditions, never model prose or health data."""
    goals = []
    evidence_by_kind = {"query": "read_result", "sync": "sync_result", "write": "write_receipt"}
    for raw in values or ():
        if not isinstance(raw, dict) or raw.get("status") not in _ACTION_STATUSES:
            continue
        kind = raw.get("kind")
        if kind not in {*evidence_by_kind, "answer"}:
            continue
        goal = {"goal_id": str(raw.get("goal_id") or kind)[:80], "kind": kind, "status": raw["status"]}
        if raw.get("evidence_kind") in evidence_by_kind.values():
            goal["evidence_kind"] = raw["evidence_kind"]
        if isinstance(raw.get("reason_code"), str):
            goal["reason_code"] = raw["reason_code"][:120]
        if goal["status"] == "verified" and kind in evidence_by_kind and goal.get("evidence_kind") != evidence_by_kind[kind]:
            goal.update(status="failed", reason_code="missing_goal_evidence")
        goals.append(goal)
    return goals


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
    goal_outcomes: Iterable[dict[str, Any]] = (),
    output_quality_flags: Iterable[str] = (),
    medical_boundary_flags: Iterable[str] = (),
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
    raw_actions = tuple(action for action in (action_outcomes or ()) if isinstance(action, dict))
    actions = _public_action_outcomes(raw_actions)
    goals = _goal_evidence_outcomes(goal_outcomes)

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
            **({"goals": goals[:32]} if goals else {}),
        }

    missing_claimed_receipt = (
        max(0, int(claimed_write_action_count or 0)) > verified_receipt_count
    )
    if (
        write_reconciliation_required or missing_claimed_receipt
        or (dispatch_started and failures)
        or any(action.get("status") == "reconciliation_required" for action in raw_actions)
        or any(goal["status"] == "reconciliation_required" for goal in goals)
    ):
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
    failed_action = next((action for action in raw_actions if action.get("status") in {"failed", "rejected"}), None)
    if failed_action is not None:
        return outcome(
            status="failed", category="action_not_executed",
            reason_code=str(failed_action.get("reason_code") or "action_not_executed")[:240],
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
    for action in raw_actions:
        if action.get("status") == "waiting_for_user":
            return outcome(
                status="waiting_for_user", category="confirmation_required",
                reason_code=action.get("reason_code") or "confirmation_required",
                retryable=False, confirmation_required=True,
            )
    if any(goal["status"] == "waiting_for_user" for goal in goals):
        return outcome(
            status="waiting_for_user", category="confirmation_required",
            reason_code="confirmation_required", retryable=False,
            confirmation_required=True,
        )
    if tuple(medical_boundary_flags):
        return outcome(
            status="blocked", category="medical_evidence_required",
            reason_code="medical_evidence_required", retryable=False,
        )

    if "protocol_leak" in output_quality_flags:
        return outcome(
            status="failed", category="invalid_answer", reason_code="protocol_leak",
            retryable=not bool(dispatch_started or verified_receipt_count),
        )

    failed_goals = [goal for goal in goals if goal["status"] in {"failed", "rejected"}]
    if failed_goals:
        partial = any(goal["status"] == "verified" for goal in goals)
        return outcome(
            status="partial" if partial else "failed",
            category="partial_goal_completion" if partial else "action_not_executed",
            reason_code="partial_goal_completion" if partial else failed_goals[0].get("reason_code", "goal_not_completed"),
            retryable=False,
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
