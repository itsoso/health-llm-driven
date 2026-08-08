"""Deterministic tool capability policy for XiaoBa Agent Kernel."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from app.services.agent_kernel.tool_registry import (
    ToolRegistryError,
    get_tool_spec,
    list_tool_specs,
)
from app.services.agent_kernel.types import CapabilityDecision, ToolExecutionRequest, TurnSnapshot
from app.services.agent_kernel.write_safety import (
    is_explicit_aigc_media_provider_veto,
    is_explicit_write_cancellation,
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
_CAPABILITY_POLICY_CONTRACT_VERSION = "agent-capability-policy-v1"
_WHOLE_RECORD_DELETE_EVIDENCE_VERSION = "record-delete-evidence-v2"
_HEALTH_MANAGE_CANONICAL_RECORD_TYPES = frozenset({
    "diet",
    "water",
    "weight",
    "waist",
    "blood_pressure",
    "sleep",
    "mood",
    "excretion",
    "exercise",
    "illness",
    "symptom",
    "medication",
    "medication_log",
    "supplement",
    "supplement_definition",
    "reminder",
    "goal",
    "medical_exam",
    "event",
    "rhinitis",
})
_DELETE_RECORD_TYPE_TEXT_ALIASES = {
    "diet": "diet",
    "food": "diet",
    "foods": "diet",
    "meal": "diet",
    "meals": "diet",
    "nutrition": "diet",
    "饮食": "diet",
    "膳食": "diet",
    "餐食": "diet",
    "早餐": "diet",
    "午餐": "diet",
    "晚餐": "diet",
    "water": "water",
    "hydration": "water",
    "饮水": "water",
    "喝水": "water",
    "weight": "weight",
    "体重": "weight",
    "waist": "waist",
    "腰围": "waist",
    "blood_pressure": "blood_pressure",
    "blood-pressure": "blood_pressure",
    "bloodpressure": "blood_pressure",
    "bp": "blood_pressure",
    "血压": "blood_pressure",
    "sleep": "sleep",
    "睡眠": "sleep",
    "mood": "mood",
    "心情": "mood",
    "情绪": "mood",
    "excretion": "excretion",
    "bowel": "excretion",
    "排便": "excretion",
    "大便": "excretion",
    "exercise": "exercise",
    "workout": "exercise",
    "运动": "exercise",
    "锻炼": "exercise",
    "illness": "illness",
    "生病": "illness",
    "symptom": "symptom",
    "symptoms": "symptom",
    "症状": "symptom",
    "medication_log": "medication_log",
    "medication-log": "medication_log",
    "用药日志": "medication_log",
    "服药日志": "medication_log",
    "medication": "medication",
    "medications": "medication",
    "medicine": "medication",
    "meds": "medication",
    "用药": "medication",
    "药物": "medication",
    "supplement_definition": "supplement_definition",
    "supplement-definition": "supplement_definition",
    "补剂定义": "supplement_definition",
    "supplement": "supplement",
    "supplements": "supplement",
    "补剂": "supplement",
    "reminder": "reminder",
    "提醒": "reminder",
    "goal": "goal",
    "目标": "goal",
    "medical_exam": "medical_exam",
    "medical-exam": "medical_exam",
    "labs": "medical_exam",
    "lab": "medical_exam",
    "体检": "medical_exam",
    "化验": "medical_exam",
    "event": "event",
    "events": "event",
    "事件": "event",
    "rhinitis": "rhinitis",
    "鼻炎": "rhinitis",
}
_WHOLE_RECORD_DELETE_VERBS = (
    "删除",
    "删掉",
    "删去",
    "删了",
    "移除",
    "清除",
    "清掉",
    "去掉",
)
_DELETE_UNDO_MARKERS = ("撤销", "取消", "恢复", "还原", "回退")
_DELETE_MIXED_UPDATE_MARKERS = (
    "修改",
    "更改",
    "更新",
    "改成",
    "改为",
    "调整",
    "修正",
)
_DELETE_RECORD_TYPE_TEXT_ALIAS_PATTERN = "|".join(
    re.escape(alias)
    for alias in sorted(
        _DELETE_RECORD_TYPE_TEXT_ALIASES,
        key=len,
        reverse=True,
    )
)
_EXACT_RECORD_TARGET_PATTERN = (
    rf"(?:{_DELETE_RECORD_TYPE_TEXT_ALIAS_PATTERN})"
    rf"(?:记录|条目)#?\d+"
)
_DELETE_REQUEST_PREFIXES = (
    "请你帮我",
    "麻烦你帮我",
    "麻烦帮我",
    "可以帮我",
    "能否帮我",
    "能不能帮我",
    "请帮我",
    "请你",
    "请您",
    "麻烦你",
    "请帮忙",
    "麻烦帮忙",
    "请替我",
    "帮我",
    "帮忙",
    "麻烦",
    "能否",
    "能不能",
    "可以",
    "替我",
    "我要",
    "给我",
    "确认",
    "请",
)
_DELETE_REQUEST_PREFIX_PATTERN = "|".join(
    re.escape(prefix)
    for prefix in sorted(_DELETE_REQUEST_PREFIXES, key=len, reverse=True)
)
_WHOLE_RECORD_DELETE_VERB_PATTERN = "|".join(
    re.escape(verb)
    for verb in sorted(_WHOLE_RECORD_DELETE_VERBS, key=len, reverse=True)
)
_DELETE_REQUEST_SUFFIX_PATTERN = (
    r"(?:一下)?(?:吧)?"
    r"(?:[,，]?(?:谢谢(?:你)?|可以吗|好吗|行吗))?"
    r"[。.!！?？]*(?:🩺)?"
)
_WHOLE_RECORD_DELETE_VERB_FIRST_RE = re.compile(
    rf"^(?:(?:{_DELETE_REQUEST_PREFIX_PATTERN}))?"
    rf"(?:{_WHOLE_RECORD_DELETE_VERB_PATTERN})"
    rf"(?P<target>{_EXACT_RECORD_TARGET_PATTERN})"
    rf"{_DELETE_REQUEST_SUFFIX_PATTERN}$",
    re.IGNORECASE,
)
_WHOLE_RECORD_DELETE_TARGET_FIRST_RE = re.compile(
    rf"^(?:(?:{_DELETE_REQUEST_PREFIX_PATTERN}))?"
    rf"(?:把|将)(?P<target>{_EXACT_RECORD_TARGET_PATTERN})"
    rf"(?:{_WHOLE_RECORD_DELETE_VERB_PATTERN})"
    rf"{_DELETE_REQUEST_SUFFIX_PATTERN}$",
    re.IGNORECASE,
)
_EXACT_RECORD_TARGET_RE = re.compile(
    rf"^(?P<record_type_alias>{_DELETE_RECORD_TYPE_TEXT_ALIAS_PATTERN})"
    r"(?:记录|条目)#?(?P<record_id>\d+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _WholeRecordDeleteEvidence:
    """Content-free authorization evidence derived only from the user turn."""

    target_kind: str
    record_type: str | None = None
    record_id: int | None = None


def canonical_health_manage_record_id(value: Any) -> int | None:
    """Return a strict positive-integer record identity, or fail closed."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        normalized = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"\d+", stripped) is None:
            return None
        normalized = int(stripped)
    else:
        return None
    return normalized if normalized > 0 else None


def canonical_health_manage_record_type(value: Any) -> str | None:
    """Accept only production-supported canonical health_manage types."""
    normalized = str(value or "").strip().lower()
    return (
        normalized
        if normalized in _HEALTH_MANAGE_CANONICAL_RECORD_TYPES
        else None
    )


def _whole_record_delete_evidence(
    text: str,
) -> _WholeRecordDeleteEvidence | None:
    """Extract content-free target evidence from a closed delete grammar."""
    normalized = "".join(str(text or "").split())
    if not normalized:
        return None
    if any(marker in normalized for marker in _DELETE_UNDO_MARKERS):
        return None
    if any(marker in normalized for marker in _DELETE_MIXED_UPDATE_MARKERS):
        return None
    match = _WHOLE_RECORD_DELETE_VERB_FIRST_RE.fullmatch(normalized)
    if match is None:
        match = _WHOLE_RECORD_DELETE_TARGET_FIRST_RE.fullmatch(normalized)
    if match is None:
        return None

    exact_target = _EXACT_RECORD_TARGET_RE.fullmatch(match.group("target"))
    if exact_target is None:
        return None
    record_id = canonical_health_manage_record_id(
        exact_target.group("record_id")
    )
    if record_id is None:
        return None
    record_type = _DELETE_RECORD_TYPE_TEXT_ALIASES.get(
        exact_target.group("record_type_alias").lower()
    )
    if record_type is None:
        return None
    return _WholeRecordDeleteEvidence(
        target_kind="exact_record",
        record_type=record_type,
        record_id=record_id,
    )


def _delete_evidence_authorizes_request(
    evidence: _WholeRecordDeleteEvidence | None,
    args: dict[str, Any],
) -> bool:
    if evidence is None or evidence.target_kind != "exact_record":
        return False
    requested_type = canonical_health_manage_record_type(args.get("record_type"))
    requested_id = canonical_health_manage_record_id(args.get("record_id"))
    if requested_type is None or requested_id is None:
        return False
    return (
        evidence.record_type == requested_type
        and evidence.record_id == requested_id
    )


def capability_policy_contract_payload() -> dict[str, Any]:
    """Return static, content-free metadata that governs tool authorization."""
    return {
        "contract_version": _CAPABILITY_POLICY_CONTRACT_VERSION,
        "whole_record_delete_evidence_version": (
            _WHOLE_RECORD_DELETE_EVIDENCE_VERSION
        ),
        "read_only_tools": sorted(READ_ONLY_TOOLS),
        "specialist_read_only_tools": sorted(SPECIALIST_READ_ONLY_TOOLS),
        "write_tools": sorted(WRITE_TOOL_NAMES),
        "known_tools": sorted(KNOWN_TOOL_NAMES),
        "manage_write_operations": sorted(MANAGE_WRITE_OPERATIONS),
        "intervention_write_actions": sorted(INTERVENTION_WRITE_ACTIONS),
        "intervention_read_actions": sorted(INTERVENTION_READ_ACTIONS),
        "manage_plan_actions": sorted(MANAGE_PLAN_ACTIONS),
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
            if primary == "mutate" and snapshot.intent.operation == operation:
                if (
                    operation == "delete"
                    and not _delete_evidence_authorizes_request(
                        _whole_record_delete_evidence(snapshot.envelope.text),
                        args,
                    )
                ):
                    return _decision(
                        "block",
                        "delete_requires_explicit_whole_record_intent",
                        tool_name,
                        args,
                        receipt_required=True,
                    )
                return _decision(
                    "allow",
                    "explicit_mutation_intent",
                    tool_name,
                    args,
                    receipt_required=True,
                )
            if primary == "mutate" and snapshot.intent.operation in MANAGE_WRITE_OPERATIONS:
                return _decision(
                    "block",
                    "manage_operation_mismatch",
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
