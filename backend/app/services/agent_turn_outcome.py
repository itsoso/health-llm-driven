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

    if confirmations:
        return {
            "category": "confirmation_required",
            "reason_code": confirmations[0],
            "retryable": False,
            "refusal_detected": False,
            "capability_block_count": len(blocks),
            "tool_failure_count": len(failures),
            "confirmation_required": True,
        }
    if blocks:
        return {
            "category": "tool_blocked",
            "reason_code": blocks[0],
            "retryable": False,
            "refusal_detected": False,
            "capability_block_count": len(blocks),
            "tool_failure_count": len(failures),
            "confirmation_required": False,
        }
    if failures:
        return {
            "category": "tool_failed",
            "reason_code": failures[0],
            "retryable": True,
            "refusal_detected": False,
            "capability_block_count": 0,
            "tool_failure_count": len(failures),
            "confirmation_required": False,
        }
    if record_intent_no_tool or destructive_or_sync_no_tool:
        reason = "write_without_tool" if record_intent_no_tool else "mutation_without_tool"
        return {
            "category": "action_not_executed",
            "reason_code": reason,
            "retryable": True,
            "refusal_detected": False,
            "capability_block_count": 0,
            "tool_failure_count": 0,
            "confirmation_required": False,
        }

    if completion_status == "error":
        return {
            "category": "execution_error",
            "reason_code": "completion_error",
            "retryable": True,
            "refusal_detected": False,
            "capability_block_count": 0,
            "tool_failure_count": 0,
            "confirmation_required": False,
        }
    refusal_reason = _refusal_reason(final_text)
    if refusal_reason:
        return {
            "category": (
                "safety_refusal" if refusal_reason == "safety_boundary" else "model_refusal"
            ),
            "reason_code": refusal_reason,
            "retryable": refusal_reason == "model_scope",
            "refusal_detected": True,
            "capability_block_count": 0,
            "tool_failure_count": 0,
            "confirmation_required": False,
        }
    if not str(final_text or "").strip():
        return {
            "category": "no_answer",
            "reason_code": "empty_final_text",
            "retryable": True,
            "refusal_detected": False,
            "capability_block_count": 0,
            "tool_failure_count": 0,
            "confirmation_required": False,
        }

    return {
        "category": "success",
        "reason_code": "verified_write" if receipts else "completed",
        "retryable": False,
        "refusal_detected": False,
        "capability_block_count": 0,
        "tool_failure_count": 0,
        "confirmation_required": False,
    }
