"""Deterministic tool capability policy for XiaoBa Agent Kernel."""
from __future__ import annotations

import json
from typing import Any

from app.services.agent_kernel.tool_registry import get_tool_spec, list_tool_specs
from app.services.agent_kernel.types import CapabilityDecision, ToolExecutionRequest, TurnSnapshot

READ_ONLY_TOOLS = frozenset(
    spec.name
    for spec in list_tool_specs()
    if spec.effect == "read" and spec.adapter_kind == "executor"
)
SPECIALIST_READ_ONLY_TOOLS = frozenset(
    spec.name for spec in list_tool_specs() if spec.adapter_kind == "specialist"
)
WRITE_TOOL_NAMES = frozenset(
    spec.name for spec in list_tool_specs() if spec.effect in {"write", "mixed"}
)
KNOWN_TOOL_NAMES = READ_ONLY_TOOLS | SPECIALIST_READ_ONLY_TOOLS | WRITE_TOOL_NAMES
MANAGE_WRITE_OPERATIONS = get_tool_spec("health_manage").write_actions
INTERVENTION_WRITE_ACTIONS = get_tool_spec("intervention_cycle").write_actions
INTERVENTION_READ_ACTIONS = get_tool_spec("intervention_cycle").read_actions
MANAGE_PLAN_ACTIONS = get_tool_spec("manage_plan").write_actions

# Procedure recipes are exact-triggered routines. Their scope is intentionally
# narrower than normal one-shot health_record calls: no long-lived reminders or
# goals, no account/profile mutation, and no external ingestion jobs.
RECIPE_REPLAY_ALLOWED_RECORD_TYPES = frozenset({
    "water",
    "weight",
    "blood_pressure",
    "diet",
    "exercise",
    "waist",
    "sleep",
    "excretion",
    "mood",
    "symptom",
    "rhinitis",
})
_RECIPE_RECORD_TYPE_ALIASES = {
    "bp": "blood_pressure",
    "blood-pressure": "blood_pressure",
    "bloodpressure": "blood_pressure",
}


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

    # Procedure recipes are user-owned, exact-triggered, server-stored tool
    # sequences. Their AUTO/typed-only confirmation semantics are still applied
    # by the recipe executor before this policy runs. This source is internal to
    # AgentExecutor and deliberately authorizes only the recipe allowlisted tool.
    if request.source == "procedure_recipe_replay":
        if tool_name != "health_record":
            return _decision(
                "block",
                "recipe_replay_tool_not_allowed",
                tool_name,
                args,
                receipt_required=True,
            )
        if recipe_replay_record_type(args) not in RECIPE_REPLAY_ALLOWED_RECORD_TYPES:
            return _decision(
                "block",
                "recipe_replay_record_type_not_allowed",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "allow",
            "prevalidated_recipe_replay",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name in READ_ONLY_TOOLS:
        return _decision("allow", "read_only_tool", tool_name, args)

    if tool_name in SPECIALIST_READ_ONLY_TOOLS:
        return _decision("allow", "specialist_read_only_tool", tool_name, args)

    if (
        snapshot.intent.domain == "aigc_media"
        and tool_name in WRITE_TOOL_NAMES
        and tool_name != "draft_aigc_media"
    ):
        # An explicit AIGC request can create only a confirmation draft. It
        # must never be reinterpreted as consent to write health data merely
        # because the attached image looks like food.
        return _decision(
            "block",
            "aigc_media_turn_disallows_health_write",
            tool_name,
            args,
            receipt_required=True,
        )

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
                (
                    "ambiguous_intent_requires_clarification"
                    if primary == "unknown"
                    else "manage_write_without_mutate_intent"
                ),
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
        return _decision(
            "block",
            (
                "ambiguous_intent_requires_clarification"
                if primary == "unknown"
                else "write_tool_without_write_intent"
            ),
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
            return _decision(
                "block",
                (
                    "ambiguous_intent_requires_clarification"
                    if primary == "unknown"
                    else "intervention_write_without_mutation_intent"
                ),
                tool_name,
                args,
                receipt_required=True,
            )
        if action in INTERVENTION_READ_ACTIONS:
            return _decision("allow", "intervention_read_only_action", tool_name, args)
        return _decision(
            "block",
            "unknown_intervention_action",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name in {"manage_plan", "upload_genetic_txt", "upload_medical_exam_text"}:
        if tool_name == "manage_plan":
            action = str(args.get("action") or "").strip().lower()
            if action not in MANAGE_PLAN_ACTIONS:
                return _decision(
                    "block",
                    "unknown_manage_plan_action",
                    tool_name,
                    args,
                    receipt_required=True,
                )
        if primary in {"write", "mutate"} and snapshot.intent.is_write:
            return _decision(
                "allow",
                "explicit_write_intent",
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

    if tool_name == "draft_aigc_media":
        if (
            primary == "write"
            and snapshot.intent.domain == "aigc_media"
            and snapshot.intent.operation == "create"
        ):
            return _decision(
                "allow",
                "explicit_aigc_media_draft",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            "aigc_media_without_explicit_draft_intent",
            tool_name,
            args,
            receipt_required=True,
        )

    if tool_name in WRITE_TOOL_NAMES:
        return _decision("block", "unhandled_write_tool", tool_name, args, receipt_required=True)

    return _decision("block", "unknown_tool", tool_name, args, receipt_required=True)


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


def recipe_replay_record_type(args: dict[str, Any]) -> str:
    """Return the normalized health_record type used by recipe policy checks."""
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    for value in (
        args.get("record_type"),
        args.get("type"),
        args.get("kind"),
        data.get("record_type"),
        data.get("type"),
        data.get("kind"),
    ):
        if value is not None:
            record_type = str(value).strip().lower()
            return _RECIPE_RECORD_TYPE_ALIASES.get(record_type, record_type)
    return ""
