"""Deterministic tool capability policy for XiaoBa Agent Kernel."""
from __future__ import annotations

import json
from typing import Any

from app.services.agent_kernel.types import CapabilityDecision, ToolExecutionRequest, TurnSnapshot

READ_ONLY_TOOLS = frozenset({
    "health_query",
    "health_query_batch",
    "knowledge_search",
    "realtime_search",
    "environment_check",
    "query_genetic_profile",
    "query_lab_indicators",
    "health_analysis",
})
WRITE_TOOL_NAMES = frozenset({"health_record", "health_manage", "intervention_cycle"})
MANAGE_WRITE_OPERATIONS = frozenset({"update", "delete"})
INTERVENTION_WRITE_ACTIONS = frozenset({"start", "update", "cancel"})


def decide_tool_capability(
    snapshot: TurnSnapshot,
    request: ToolExecutionRequest,
) -> CapabilityDecision:
    """Return the policy decision for one tool request.

    This function is intentionally independent from prompt text and tool schema
    exposure. It evaluates the turn intent plus normalized tool arguments.
    """
    tool_name = str(request.tool_name or "").strip()
    args = _parse_args(request.arguments)
    primary = snapshot.intent.primary

    if not tool_name:
        return _decision("block", "missing_tool_name", tool_name, args)

    if tool_name in READ_ONLY_TOOLS:
        return _decision("allow", "read_only_tool", tool_name, args)

    if tool_name == "health_manage":
        operation = str(args.get("operation") or "").strip().lower()
        if operation == "list":
            return _decision("allow", "health_manage_list_is_read_only", tool_name, args)
        if operation in MANAGE_WRITE_OPERATIONS:
            if primary == "mutate" and snapshot.intent.operation in MANAGE_WRITE_OPERATIONS:
                return _decision(
                    "allow",
                    "explicit_mutation_intent",
                    tool_name,
                    args,
                    receipt_required=True,
                )
            return _decision(
                "block",
                "manage_write_without_mutate_intent",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision("block", "unknown_health_manage_operation", tool_name, args)

    if tool_name == "health_record":
        if primary == "write" and snapshot.intent.operation == "create":
            return _decision(
                "allow",
                "explicit_create_intent",
                tool_name,
                args,
                receipt_required=True,
            )
        if primary == "unknown":
            return _decision(
                "allow",
                "legacy_unknown_intent_write",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            "write_tool_without_write_intent",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name == "intervention_cycle":
        action = str(args.get("action") or "").strip().lower()
        if action in INTERVENTION_WRITE_ACTIONS:
            if primary in {"write", "mutate"}:
                return _decision(
                    "allow",
                    "explicit_intervention_write_intent",
                    tool_name,
                    args,
                    receipt_required=True,
                )
            if primary == "unknown":
                return _decision(
                    "allow",
                    "legacy_unknown_intent_intervention_write",
                    tool_name,
                    args,
                    receipt_required=True,
                )
            return _decision(
                "block",
                "intervention_write_without_mutation_intent",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision("allow", "intervention_read_or_unknown_action", tool_name, args)

    if tool_name in WRITE_TOOL_NAMES:
        return _decision("block", "unhandled_write_tool", tool_name, args, receipt_required=True)

    return _decision("allow", "non_write_tool_not_policy_gated", tool_name, args)


def _decision(
    action: str,
    reason: str,
    tool_name: str,
    args: dict[str, Any],
    *,
    receipt_required: bool = False,
) -> CapabilityDecision:
    return CapabilityDecision(
        action=action,
        reason=reason,
        normalized_tool_name=tool_name or None,
        normalized_args=args,
        receipt_required=receipt_required,
    )


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    try:
        return dict(raw or {})
    except (TypeError, ValueError):
        return {}
