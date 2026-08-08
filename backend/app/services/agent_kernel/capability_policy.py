"""Deterministic tool capability policy for XiaoBa Agent Kernel."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.services.agent_kernel.tool_registry import (
    ToolRegistryError,
    get_tool_spec,
    list_tool_specs,
)
from app.services.agent_kernel.types import (
    AgentEnvelope,
    CapabilityDecision,
    ToolExecutionRequest,
    TurnSnapshot,
)
from app.services.agent_kernel.write_safety import (
    has_mixed_health_record_authorization,
    is_explicit_aigc_media_provider_veto,
    is_non_authorizing_write_reference,
    is_explicit_write_cancellation,
    lacks_positive_health_record_authorization,
)
from app.services.clinician_provenance_guard import classify_clinician_turn

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
_CAPABILITY_POLICY_CONTRACT_VERSION = "agent-capability-policy-v2"
_HEALTH_RECORD_TARGET_BINDING_VERSION = "clause-target-v1"
_HEALTH_RECORD_DOMAIN_TYPES = {
    "diet": "diet",
    "water": "water",
    "medication": "medication",
    "supplement": "supplement",
    "symptom": "symptom",
}
_METRIC_RECORD_TYPE_TERMS = (
    ("blood_pressure", ("血压", "高压", "低压", "收缩压", "舒张压")),
    ("weight", ("体重", "称重", "kg", "公斤", "千克", "斤")),
    ("waist", ("腰围",)),
    ("sleep", ("睡眠", "入睡", "起床")),
    ("exercise", ("运动", "训练", "跑步", "步数", "走了")),
)
_ILLNESS_TARGET_TERMS = (
    "口腔溃疡",
    "舌尖溃疡",
    "嘴唇起泡",
    "麦粒肿",
    "甲沟炎",
    "带状疱疹",
    "感冒",
    "流感",
    "湿疹",
    "烫伤",
    "水泡",
    "伤口",
    "痘痘发作",
)
_MEAL_TYPE_ALIASES = {
    "breakfast": "breakfast",
    "早餐": "breakfast",
    "早饭": "breakfast",
    "lunch": "lunch",
    "午餐": "lunch",
    "午饭": "lunch",
    "中饭": "lunch",
    "dinner": "dinner",
    "晚餐": "dinner",
    "晚饭": "dinner",
    "snack": "snack",
    "加餐": "snack",
    "零食": "snack",
    "夜宵": "snack",
}
_WEIGHT_TARGET_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)(?P<unit>kg|公斤|千克|斤)", re.IGNORECASE
)
_BLOOD_PRESSURE_TARGET_RE = re.compile(r"(?P<systolic>\d{2,3})[/／](?P<diastolic>\d{2,3})")
_WAIST_TARGET_RE = re.compile(r"腰围(?P<value>\d+(?:\.\d+)?)(?:cm|厘米)?", re.IGNORECASE)


def capability_policy_contract_payload() -> dict[str, Any]:
    """Return static, content-free metadata that governs tool authorization."""
    return {
        "contract_version": _CAPABILITY_POLICY_CONTRACT_VERSION,
        "read_only_tools": sorted(READ_ONLY_TOOLS),
        "specialist_read_only_tools": sorted(SPECIALIST_READ_ONLY_TOOLS),
        "write_tools": sorted(WRITE_TOOL_NAMES),
        "known_tools": sorted(KNOWN_TOOL_NAMES),
        "manage_write_operations": sorted(MANAGE_WRITE_OPERATIONS),
        "intervention_write_actions": sorted(INTERVENTION_WRITE_ACTIONS),
        "intervention_read_actions": sorted(INTERVENTION_READ_ACTIONS),
        "manage_plan_actions": sorted(MANAGE_PLAN_ACTIONS),
        "health_record_target_binding": {
            "version": _HEALTH_RECORD_TARGET_BINDING_VERSION,
            "domain_types": dict(sorted(_HEALTH_RECORD_DOMAIN_TYPES.items())),
        },
        "recipe_record_types": sorted(RECIPE_REPLAY_ALLOWED_RECORD_TYPES),
        "recipe_record_type_aliases": dict(
            sorted(_RECIPE_RECORD_TYPE_ALIASES.items())
        ),
    }


def capability_policy_digest() -> str:
    """Fingerprint policy metadata without prompts, arguments or user content."""
    encoded = json.dumps(
        capability_policy_contract_payload(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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

    mutating_request = _is_mutating_request(tool_name, args)
    if (
        tool_name == "draft_aigc_media"
        and is_explicit_aigc_media_provider_veto(snapshot.envelope.text)
    ):
        return _decision(
            "block",
            "explicit_aigc_media_provider_veto",
            tool_name,
            args,
            receipt_required=True,
        )
    if (
        mutating_request
        and is_explicit_write_cancellation(snapshot.envelope.text)
    ):
        return _decision(
            "block",
            "explicit_write_cancellation",
            tool_name,
            args,
            receipt_required=True,
        )
    if (
        tool_name == "health_record"
        and is_non_authorizing_write_reference(snapshot.envelope.text)
    ):
        return _decision(
            "block",
            "write_tool_without_write_intent",
            tool_name,
            args,
            receipt_required=True,
        )
    if (
        tool_name == "health_record"
        and primary == "write"
        and lacks_positive_health_record_authorization(snapshot.envelope.text)
    ):
        return _decision(
            "block",
            "write_tool_without_direct_authorization",
            tool_name,
            args,
            receipt_required=True,
        )
    if (
        tool_name == "health_record"
        and request.source != "procedure_recipe_replay"
    ):
        target_status = _health_record_target_status(snapshot, args)
        if target_status == "mismatch":
            return _decision(
                "block",
                "health_record_target_mismatch",
                tool_name,
                args,
                receipt_required=True,
            )
        if target_status == "unresolved":
            return _decision(
                "block",
                "health_record_authorization_target_unresolved",
                tool_name,
                args,
                receipt_required=True,
            )
    if (
        mutating_request
        and snapshot.goal is not None
        and snapshot.goal.requires_clarification
    ):
        return _decision(
            "block",
            "goal_requires_clarification",
            tool_name,
            args,
            receipt_required=True,
        )

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

    if request.source == "telegram_directive":
        if tool_name != "user_directive":
            return _decision(
                "block",
                "telegram_directive_tool_not_allowed",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "allow",
            "prevalidated_telegram_directive",
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

    if tool_name == "record_doctor_feedback":
        clinician_decision = classify_clinician_turn(snapshot.envelope.text)
        explicit_clinician_write = (
            primary == "write"
            and snapshot.intent.domain == "clinical_context"
            and snapshot.intent.operation == "create"
            and snapshot.intent.is_write
            and clinician_decision.authorizes_feedback_write
        )
        if explicit_clinician_write:
            return _decision(
                "allow",
                "explicit_doctor_feedback_write",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            "doctor_feedback_without_explicit_clinician_write",
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

    if tool_name == "user_directive":
        if primary in {"write", "mutate"} and snapshot.intent.is_write:
            return _decision(
                "allow",
                "explicit_user_directive",
                tool_name,
                args,
                receipt_required=True,
            )
        return _decision(
            "block",
            "user_directive_without_write_intent",
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


def _is_mutating_request(tool_name: str, args: dict[str, Any]) -> bool:
    try:
        return get_tool_spec(tool_name).classify_effect(args) == "write"
    except ToolRegistryError:
        return tool_name in WRITE_TOOL_NAMES


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


def _health_record_target_status(
    snapshot: TurnSnapshot,
    args: dict[str, Any],
) -> str:
    """Bind a health_record request to the final direct authorized clause."""
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.write_intent_scope import governing_authorized_write_clause

    clause = governing_authorized_write_clause(snapshot.envelope.text)
    if not clause:
        return "unresolved" if has_mixed_health_record_authorization(
            snapshot.envelope.text
        ) else "unknown"

    clause_envelope = AgentEnvelope(
        user_id=snapshot.envelope.user_id,
        channel=snapshot.envelope.channel,
        text=clause,
        source_message_id=snapshot.envelope.source_message_id,
        client_capabilities=snapshot.envelope.client_capabilities,
        client_time_context=snapshot.envelope.client_time_context,
        client_turn_id=snapshot.envelope.client_turn_id,
    )
    clause_intent = build_intent_frame(clause_envelope, snapshot.context)
    clause_goal = compile_goal_spec(
        envelope=clause_envelope,
        context=snapshot.context,
        intent=clause_intent,
    )
    expected_types = _authorized_record_types(
        clause,
        clause_intent.domain,
        str(clause_goal.target_record_type or "").strip().lower(),
    )
    mixed_polarity = has_mixed_health_record_authorization(
        snapshot.envelope.text
    )
    snapshot_goal_type = (
        str(snapshot.goal.target_record_type or "").strip().lower()
        if snapshot.goal is not None
        else ""
    )
    if not expected_types and snapshot_goal_type and not mixed_polarity:
        expected_types = frozenset({snapshot_goal_type})
    if not expected_types:
        return "unresolved" if mixed_polarity else "unknown"

    requested_type = recipe_replay_record_type(args)
    if requested_type and requested_type not in expected_types:
        return "mismatch"
    if not requested_type:
        return "match"

    clause_goal_type = str(clause_goal.target_record_type or "").strip().lower()
    expected_values = dict(clause_goal.target_values) if (
        requested_type == clause_goal_type
    ) else {}
    if (
        not expected_values
        and snapshot.goal is not None
        and not mixed_polarity
        and requested_type == snapshot_goal_type
    ):
        expected_values = dict(snapshot.goal.target_values)
    if requested_type == "diet" and clause_goal.target_meal_types:
        expected_values["meal_types"] = clause_goal.target_meal_types
    elif requested_type == "diet" and clause_intent.scope.get("meal_type"):
        expected_values["meal_types"] = (clause_intent.scope["meal_type"],)
    expected_values.update(
        _deterministic_target_values(clause, requested_type)
    )
    return (
        "mismatch"
        if _target_values_mismatch(requested_type, expected_values, args)
        else "match"
    )


def _authorized_record_types(
    clause: str,
    domain: str,
    goal_record_type: str,
) -> frozenset[str]:
    record_types: set[str] = set()
    if goal_record_type:
        record_types.add(goal_record_type)
    if "鼻炎" in clause:
        record_types.add("rhinitis")
    if any(term in clause for term in _ILLNESS_TARGET_TERMS):
        record_types.add("illness")
    for record_type, terms in _METRIC_RECORD_TYPE_TERMS:
        if any(term in clause for term in terms):
            record_types.add(record_type)
    if domain in _HEALTH_RECORD_DOMAIN_TYPES:
        record_types.add(_HEALTH_RECORD_DOMAIN_TYPES[domain])
    return frozenset(record_types)


def _deterministic_target_values(
    clause: str,
    record_type: str,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if record_type == "weight" and (match := _WEIGHT_TARGET_RE.search(clause)):
        weight = float(match.group("value"))
        if match.group("unit") == "斤":
            weight /= 2
        values["weight"] = weight
    elif record_type == "blood_pressure" and (
        match := _BLOOD_PRESSURE_TARGET_RE.search(clause)
    ):
        values["systolic"] = int(match.group("systolic"))
        values["diastolic"] = int(match.group("diastolic"))
    elif record_type == "waist" and (match := _WAIST_TARGET_RE.search(clause)):
        values["waist_cm"] = float(match.group("value"))
    elif record_type == "illness":
        illness = next(
            (term for term in _ILLNESS_TARGET_TERMS if term in clause),
            "",
        )
        if illness:
            values["name"] = illness
    return values


def _target_values_mismatch(
    record_type: str,
    expected: dict[str, Any],
    args: dict[str, Any],
) -> bool:
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    if record_type == "diet" and expected.get("meal_types"):
        requested_meal = _MEAL_TYPE_ALIASES.get(
            str(data.get("meal_type") or args.get("meal_type") or "").strip().lower(),
            "",
        )
        allowed_meals = {
            _MEAL_TYPE_ALIASES.get(str(value).strip().lower(), str(value).strip().lower())
            for value in expected["meal_types"]
        }
        if requested_meal and requested_meal not in allowed_meals:
            return True

    numeric_keys = {
        "water": (("amount_ml", "amount"), expected.get("amount_ml")),
        "weight": (("weight",), expected.get("weight")),
        "blood_pressure": (("systolic",), expected.get("systolic")),
        "waist": (("waist_cm",), expected.get("waist_cm")),
    }
    if record_type in numeric_keys:
        keys, expected_number = numeric_keys[record_type]
        requested_number = next(
            (data[key] for key in keys if data.get(key) is not None),
            None,
        )
        if (
            expected_number is not None
            and requested_number is not None
            and not _numbers_match(expected_number, requested_number)
        ):
            return True
    if record_type == "blood_pressure" and expected.get("diastolic") is not None:
        requested_diastolic = data.get("diastolic")
        if requested_diastolic is not None and not _numbers_match(
            expected["diastolic"], requested_diastolic
        ):
            return True
    if record_type == "illness" and expected.get("name"):
        requested_name = str(
            data.get("name") or data.get("illness_name") or ""
        ).strip()
        if requested_name and expected["name"] not in requested_name:
            return True
    return False


def _numbers_match(expected: Any, requested: Any) -> bool:
    try:
        return abs(float(expected) - float(requested)) < 1e-6
    except (TypeError, ValueError):
        return str(expected).strip() == str(requested).strip()
