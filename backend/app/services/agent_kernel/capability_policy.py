"""Deterministic tool capability policy for XiaoBa Agent Kernel."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
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
_CAPABILITY_POLICY_CONTRACT_VERSION = "agent-capability-policy-v5"
_HEALTH_RECORD_TARGET_BINDING_VERSION = "authorized-target-set-v4"
_HEALTH_RECORD_DOMAIN_TYPES = {
    "diet": "diet",
    "water": "water",
    "medication": "medication",
    "supplement": "supplement",
    "symptom": "symptom",
    "reminder": "reminder",
    "mood": "mood",
    "exercise": "exercise",
    "sleep": "sleep",
}
_METRIC_RECORD_TYPE_TERMS = (
    ("blood_pressure", ("血压", "高压", "低压", "收缩压", "舒张压")),
    ("weight", ("体重", "称重", "kg", "公斤", "千克", "斤")),
    ("waist", ("腰围",)),
    ("sleep", ("睡眠", "睡觉", "入睡", "起床")),
    ("exercise", ("运动", "训练", "跑步", "步数", "走了")),
)
_EXPLICIT_RECORD_TYPE_TERMS = (
    ("water", ("喝水", "饮水", "补水", "ml水", "毫升水")),
    (
        "diet",
        (
            "早餐",
            "早饭",
            "午餐",
            "午饭",
            "中饭",
            "晚餐",
            "晚饭",
            "加餐",
            "零食",
            "夜宵",
        ),
    ),
    ("medication", ("吃药", "服药", "用药", "药物", "药片", "胶囊")),
    ("supplement", ("补剂", "维生素", "益生菌", "鱼油")),
    ("symptom", ("头痛", "头疼", "眼痒", "嗓子疼", "不适", "症状")),
    ("mood", ("心情", "情绪", "心境")),
    ("excretion", ("排便", "大便", "便秘", "腹泻")),
    ("reminder", ("提醒", "闹钟")),
    ("goal", ("目标",)),
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
_WATER_TARGET_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ml|毫升|l|升)(?:的)?(?:水)?",
    re.IGNORECASE,
)
_WRITE_TARGET_ACTION_RE = re.compile(
    r"(?:记录|记一下|记下|打个卡|打卡|新增|录入|保存|写入|存下来)"
)
_ILLNESS_SUFFIX_RE = re.compile(
    r"(?:炎|病|症|癌|疹|感染|溃疡|感冒|流感|疱疹|烫伤|水泡|伤口)$"
)
_SUPPLEMENT_TARGET_TERMS = (
    "鱼油",
    "维生素d",
    "维d",
    "维生素c",
    "维c",
    "复合维生素",
    "益生菌",
    "镁",
    "钙",
    "辅酶q10",
    "红参液",
)
_MEDICATION_TARGET_TERMS = (
    "二甲双胍",
)
_MEDICATION_DOSE_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?|[一二两三四五六七八九十])\s*"
    r"(?P<unit>片|粒|丸|袋|支|mg|g|mcg|ug|μg|毫克|克|ml|毫升)",
    re.IGNORECASE,
)
_MEDICATION_STRENGTH_RE = re.compile(
    r"(?:每(?:片|粒|丸|袋|支)|规格(?:是|为)?)\s*"
    r"(?P<value>\d+(?:\.\d+)?|[一二两三四五六七八九十])\s*"
    r"(?P<unit>mg|g|mcg|ug|μg|毫克|克|ml|毫升)",
    re.IGNORECASE,
)
_MEDICATION_NAME_SUFFIX_RE = re.compile(
    r"(?:霉素|必利|瑞酮|二甲双胍|沙坦|普利|洛尔|他汀|唑仑|西泮)$"
)
_CHINESE_DOSE_NUMBERS = {
    "一": "1",
    "二": "2",
    "两": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
}
_EXERCISE_TARGET_TERMS = (
    "跑步",
    "散步",
    "走路",
    "游泳",
    "骑车",
    "骑行",
    "力量训练",
    "瑜伽",
)
_EXERCISE_DURATION_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>分钟|小时|min|h)",
    re.IGNORECASE,
)
_MOOD_SCORE_RE = re.compile(r"(?:心情|情绪|心境).{0,6}?(?P<value>[1-5])\s*分")
_MOOD_TARGET_TERMS = (
    "calm",
    "平静",
    "开心",
    "愉快",
    "低落",
    "焦虑",
    "烦躁",
    "生气",
)
_MOOD_TARGET_ALIASES = {
    "calm": "calm",
    "平静": "calm",
    "开心": "happy",
    "愉快": "happy",
    "低落": "low",
    "焦虑": "anxious",
    "烦躁": "irritable",
    "生气": "angry",
}
_EXCRETION_TARGET_ALIASES = {
    "bowel": "bowel",
    "排便": "bowel",
    "大便": "bowel",
    "constipation": "constipation",
    "便秘": "constipation",
    "diarrhea": "diarrhea",
    "腹泻": "diarrhea",
}
_CLOCK_RE = re.compile(r"(?<!\d)(?P<hour>[01]?\d|2[0-3])[:：点](?P<minute>[0-5]\d)?")
_SLEEP_QUALITY_RE = re.compile(r"(?:睡眠)?质量.{0,3}(?P<value>[1-5])\s*分?")
_SEVERITY_TARGET_RE = re.compile(
    r"(?:严重程度|严重度|程度|强度)?\s*(?P<value>10|[1-9])\s*(?:分(?!钟)|级)"
)


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
    if tool_name == "health_record":
        args = normalize_health_record_dispatch_args(args)
    primary = snapshot.intent.primary
    health_record_target_authorized = False

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
    if mutating_request and is_explicit_write_cancellation(
        snapshot.envelope.text
    ):
        mixed_health_record_target = False
        if tool_name == "health_record":
            from app.services.write_intent_scope import (
                authorized_health_record_clauses,
            )

            mixed_health_record_target = bool(
                authorized_health_record_clauses(snapshot.envelope.text)
            )
        if not mixed_health_record_target:
            return _decision(
                "block",
                "explicit_write_cancellation",
                tool_name,
                args,
                receipt_required=True,
            )
    if (
        tool_name == "health_record"
        and snapshot.intent.domain == "aigc_media"
    ):
        return _decision(
            "block",
            "aigc_media_turn_disallows_health_write",
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
        health_record_target_authorized = target_status == "match"
        if target_status == "unauthorized":
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
        if health_record_target_authorized:
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


def normalize_health_record_dispatch_args(
    args: dict[str, Any],
) -> dict[str, Any]:
    """Canonicalize aliases before both policy comparison and dispatch.

    The gateway dispatches ``CapabilityDecision.normalized_args``.  This makes
    the exact payload inspected by the authorization policy the payload later
    consumed by the executor, instead of merely *recognizing* aliases that an
    adapter would ignore.
    """
    normalized = dict(args)
    raw_data = normalized.get("data")
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    record_type = recipe_replay_record_type(normalized)

    if record_type == "illness":
        canonical_key = "start_date"
        candidates = (
            data.get("start_date"),
            data.get("record_date"),
            data.get("date"),
            normalized.get("start_date"),
            normalized.get("record_date"),
            normalized.get("date"),
        )
        name = next(
            (
                value
                for value in (
                    data.get("name"),
                    data.get("illness_name"),
                    normalized.get("name"),
                    normalized.get("illness_name"),
                )
                if value not in (None, "", [])
            ),
            None,
        )
        for container in (data, normalized):
            container.pop("name", None)
            container.pop("illness_name", None)
        if name is not None:
            data["name"] = name
        _canonicalize_top_level_fields(
            normalized,
            data,
            ("status", "notes", "severity", "end_date"),
        )
    elif record_type == "symptom":
        canonical_key = "record_date"
        candidates = (
            data.get("record_date"),
            data.get("date"),
            normalized.get("record_date"),
            normalized.get("date"),
        )
        _canonicalize_top_level_fields(
            normalized,
            data,
            ("body_part", "description", "severity", "occurred_at"),
        )
    elif record_type == "reminder":
        candidates = ()
        canonical_key = ""
    else:
        canonical_key = "record_date"
        candidates = (
            data.get("record_date"),
            data.get("date"),
            normalized.get("record_date"),
            normalized.get("date"),
        )
    canonical_date = next(
        (value for value in candidates if value not in (None, "", [])),
        None,
    )
    if canonical_key and canonical_date is not None:
        date_aliases = (
            ("start_date", "record_date", "date")
            if record_type == "illness"
            else ("record_date", "date")
        )
        for container in (data, normalized):
            for alias in date_aliases:
                container.pop(alias, None)
        data[canonical_key] = canonical_date

    if record_type == "medication":
        _canonicalize_named_field(
            normalized,
            data,
            canonical_key="medication_name",
            aliases=("medication_name", "name"),
        )
        _canonicalize_medication_aliases(normalized, data)
    elif record_type == "supplement":
        _canonicalize_named_field(
            normalized,
            data,
            canonical_key="supplement_name",
            aliases=("supplement_name", "name"),
        )
        for container in (data, normalized):
            for key in ("dosage", "timing", "category", "description"):
                container.pop(key, None)

    if isinstance(raw_data, dict) or data:
        normalized["data"] = data
    return normalized


def _canonicalize_top_level_fields(
    args: dict[str, Any],
    data: dict[str, Any],
    keys: tuple[str, ...],
) -> None:
    for key in keys:
        value = data.get(key)
        if value in (None, "", []):
            value = args.get(key)
        args.pop(key, None)
        if value not in (None, "", []):
            data[key] = value


def _canonicalize_named_field(
    args: dict[str, Any],
    data: dict[str, Any],
    *,
    canonical_key: str,
    aliases: tuple[str, ...],
) -> None:
    value = next(
        (
            container.get(alias)
            for container in (data, args)
            for alias in aliases
            if container.get(alias) not in (None, "", [])
        ),
        None,
    )
    for container in (data, args):
        for alias in aliases:
            container.pop(alias, None)
    if value is not None:
        data[canonical_key] = value


_MEDICATION_ACTUAL_VALUE_RE = re.compile(
    r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半])\s*"
    r"(?:粒|片|袋|支|丸|颗|滴|喷|毫升|ml|单位|iu|u)",
    re.IGNORECASE,
)


def _medication_alias_values(
    args: dict[str, Any],
    data: dict[str, Any],
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    actual: list[Any] = []
    strengths: list[Any] = []
    for container in (data, args):
        for key in ("actual_dosage", "dose"):
            value = container.get(key)
            if value not in (None, "", []):
                actual.append(value)
        for key in ("observed_strength", "strength"):
            value = container.get(key)
            if value not in (None, "", []):
                strengths.append(value)

    for container in (data, args):
        legacy = container.get("dosage")
        if legacy in (None, "", []):
            continue
        if _MEDICATION_ACTUAL_VALUE_RE.fullmatch(str(legacy).strip()):
            actual.append(legacy)
        else:
            strengths.append(legacy)
    return tuple(actual), tuple(strengths)


def _canonicalize_medication_aliases(
    args: dict[str, Any],
    data: dict[str, Any],
) -> None:
    actual_values, strength_values = _medication_alias_values(args, data)
    normalized_actual = {
        _normalize_medication_dosage(value)
        for value in actual_values
        if _normalize_medication_dosage(value)
    }
    normalized_strengths = {
        _normalize_medication_dosage(value)
        for value in strength_values
        if _normalize_medication_dosage(value)
    }
    if len(normalized_actual) > 1 or len(normalized_strengths) > 1:
        return
    for container in (data, args):
        for key in (
            "actual_dosage",
            "dose",
            "dosage",
            "observed_strength",
            "strength",
        ):
            container.pop(key, None)
    if actual_values:
        data["actual_dosage"] = actual_values[0]
    if strength_values:
        data["observed_strength"] = strength_values[0]


def medication_dispatch_aliases_conflict(args: dict[str, Any]) -> bool:
    """Return whether model aliases express multiple consumed medication values."""
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    actual_values, strength_values = _medication_alias_values(args, data)
    normalized_actual = {
        _normalize_medication_dosage(value)
        for value in actual_values
        if _normalize_medication_dosage(value)
    }
    normalized_strengths = {
        _normalize_medication_dosage(value)
        for value in strength_values
        if _normalize_medication_dosage(value)
    }
    return len(normalized_actual) > 1 or len(normalized_strengths) > 1


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
    """Bind one request to one member of the direct authorized target set."""
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.write_intent_scope import authorized_health_record_clauses

    clauses = authorized_health_record_clauses(snapshot.envelope.text)
    if not clauses:
        return "unauthorized"
    requested_type = recipe_replay_record_type(args)
    if not requested_type:
        return "unresolved"

    direct_write_seen = False
    matching_type_seen = False
    incomplete_target_seen = False
    default_date = snapshot.context.current_time.date().isoformat()
    for clause in clauses:
        clause_envelope = AgentEnvelope(
            user_id=snapshot.envelope.user_id,
            channel=snapshot.envelope.channel,
            text=clause,
            media=snapshot.envelope.media,
            source_message_id=snapshot.envelope.source_message_id,
            client_capabilities=snapshot.envelope.client_capabilities,
            client_time_context=snapshot.envelope.client_time_context,
            client_turn_id=snapshot.envelope.client_turn_id,
        )
        if (
            len(clauses) == 1
            and "continuation:reminder_schedule" in snapshot.intent.evidence
        ):
            clause_intent = snapshot.intent
        else:
            clause_intent = build_intent_frame(clause_envelope, snapshot.context)
        if (
            not clause_intent.is_write
            or clause_intent.primary not in {"write", "mutate"}
            or clause_intent.operation != "create"
        ):
            continue
        direct_write_seen = True
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
        if (
            not expected_types
            and len(clauses) == 1
            and snapshot.goal is not None
            and any(referent in clause for referent in ("这个", "这条", "它"))
        ):
            contextual_type = str(
                snapshot.goal.target_record_type or ""
            ).strip().lower()
            if contextual_type:
                expected_types = frozenset({contextual_type})
        if requested_type not in expected_types:
            continue
        matching_type_seen = True

        clause_goal_type = str(
            clause_goal.target_record_type or ""
        ).strip().lower()
        expected_values = (
            dict(clause_goal.target_values)
            if requested_type == clause_goal_type
            else {}
        )
        if (
            not expected_values
            and len(clauses) == 1
            and snapshot.goal is not None
            and requested_type
            == str(snapshot.goal.target_record_type or "").strip().lower()
            and any(referent in clause for referent in ("这个", "这条", "它"))
        ):
            expected_values = dict(snapshot.goal.target_values)
        if requested_type == "diet" and clause_goal.target_meal_types:
            expected_values["meal_types"] = clause_goal.target_meal_types
        elif requested_type == "diet" and clause_intent.scope.get("meal_type"):
            expected_values["meal_types"] = (
                clause_intent.scope["meal_type"],
            )
        deterministic_values = _deterministic_target_values(
            clause,
            requested_type,
        )
        if requested_type == "diet" and expected_values.get("food_items"):
            deterministic_values.pop("meal_food_targets", None)
        expected_values.update(deterministic_values)
        if (
            requested_type == "reminder"
            and "continuation:reminder_schedule" in clause_intent.evidence
        ):
            expected_values["contextual_continuation"] = True
        if (
            requested_type == "diet"
            and snapshot.envelope.media
            and any(referent in clause for referent in ("这餐", "这一餐", "这顿"))
        ):
            expected_values["attachment_authorized"] = True
        expected_values["target_date"] = clause_goal.target_date or default_date
        expected_values["default_date"] = default_date
        if requested_type == "symptom" and expected_values.get("occurred_clock"):
            target_day = date.fromisoformat(expected_values["target_date"])
            hour, minute = (
                int(value)
                for value in str(expected_values["occurred_clock"]).split(":", 1)
            )
            expected_values["canonical_occurred_at"] = (
                snapshot.context.current_time.replace(
                    year=target_day.year,
                    month=target_day.month,
                    day=target_day.day,
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                ).isoformat()
            )
        if not _authorization_target_complete(requested_type, expected_values):
            incomplete_target_seen = True
            continue
        if not _target_values_mismatch(requested_type, expected_values, args):
            return "match"

    if matching_type_seen and incomplete_target_seen:
        return "unresolved"
    if direct_write_seen:
        return "mismatch"
    return "unauthorized"


def _authorized_record_types(
    clause: str,
    domain: str,
    goal_record_type: str,
) -> frozenset[str]:
    record_types: set[str] = set()
    if goal_record_type:
        record_types.add(goal_record_type)
    if any(term in clause for term in ("提醒", "闹钟")):
        return frozenset({"reminder"})
    if "鼻炎" in clause:
        record_types.add("rhinitis")
    for record_type, terms in _EXPLICIT_RECORD_TYPE_TERMS:
        if any(term in clause for term in terms):
            record_types.add(record_type)
    if "药" in clause and not any(
        term in clause for term in ("补剂", "维生素", "益生菌", "鱼油")
    ):
        record_types.add("medication")
    if any(term in clause for term in _MEDICATION_TARGET_TERMS):
        record_types.add("medication")
    if _looks_like_medication_clause(clause):
        record_types.add("medication")
    illness_targets = _illness_targets(clause)
    if illness_targets and not (
        record_types & {"medication", "supplement"}
        and all(f"{target}药" in clause for target in illness_targets)
    ):
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
    if record_type == "water" and (
        matches := tuple(_WATER_TARGET_RE.finditer(clause))
    ):
        match = matches[-1]
        amount = float(match.group("value"))
        if match.group("unit").lower() in {"l", "升"}:
            amount *= 1000
        values["amount_ml"] = amount
    elif record_type == "weight" and (
        matches := tuple(_WEIGHT_TARGET_RE.finditer(clause))
    ):
        match = matches[-1]
        weight = float(match.group("value"))
        if match.group("unit") == "斤":
            weight /= 2
        values["weight"] = weight
    elif record_type == "blood_pressure" and (
        matches := tuple(_BLOOD_PRESSURE_TARGET_RE.finditer(clause))
    ):
        match = matches[-1]
        values["systolic"] = int(match.group("systolic"))
        values["diastolic"] = int(match.group("diastolic"))
    elif record_type == "waist" and (
        matches := tuple(_WAIST_TARGET_RE.finditer(clause))
    ):
        match = matches[-1]
        values["waist_cm"] = float(match.group("value"))
    elif record_type == "illness":
        targets = _illness_targets(clause)
        if targets:
            values["names"] = targets
        if notes := _target_text_after_marker(clause, "备注"):
            values["notes"] = notes
        if any(term in clause for term in ("已痊愈", "痊愈", "已经好了", "已好了")):
            values["status"] = "resolved"
        elif any(term in clause for term in ("好转", "改善中")):
            values["status"] = "improving"
        elif any(term in clause for term in ("发作中", "还没好", "仍未好")):
            values["status"] = "active"
    elif record_type == "diet":
        meal_food_targets = _diet_meal_food_targets(clause)
        if meal_food_targets:
            values["meal_food_targets"] = meal_food_targets
            values["meal_types"] = tuple(meal_food_targets)
    elif record_type == "medication":
        medication_details = _medication_item_details(clause)
        if medication_details:
            values["names"] = tuple(medication_details)
            dosages = {
                name: details["dosage"]
                for name, details in medication_details.items()
                if details.get("dosage")
            }
            if dosages:
                values["dosages"] = dosages
            strengths = {
                name: details["observed_strength"]
                for name, details in medication_details.items()
                if details.get("observed_strength")
            }
            if strengths:
                values["observed_strengths"] = strengths
    elif record_type == "supplement":
        names = _named_item_targets(clause, record_type)
        if names:
            values["names"] = names
    elif record_type == "symptom" and (clocks := tuple(_CLOCK_RE.finditer(clause))):
        match = clocks[-1]
        values["occurred_clock"] = (
            f"{int(match.group('hour')):02d}:"
            f"{int(match.group('minute') or 0):02d}"
        )
    elif record_type == "exercise":
        exercise_types = tuple(
            term for term in _EXERCISE_TARGET_TERMS if term in clause
        )
        if exercise_types:
            values["exercise_types"] = tuple(dict.fromkeys(exercise_types))
        duration_matches = tuple(_EXERCISE_DURATION_RE.finditer(clause))
        if duration_matches:
            duration = float(duration_matches[-1].group("value"))
            if duration_matches[-1].group("unit").lower() in {"小时", "h"}:
                duration *= 60
            values["duration_minutes"] = duration
    elif record_type == "mood" and (match := _MOOD_SCORE_RE.search(clause)):
        values["mood_score"] = int(match.group("value"))
    elif record_type == "mood":
        mood_values = tuple(term for term in _MOOD_TARGET_TERMS if term in clause)
        if mood_values:
            values["mood_values"] = tuple(dict.fromkeys(mood_values))
    elif record_type == "excretion":
        kinds: list[str] = []
        if any(term in clause for term in ("排便", "大便")):
            kinds.append("bowel")
        if "便秘" in clause:
            kinds.append("constipation")
        if "腹泻" in clause:
            kinds.append("diarrhea")
        if kinds:
            values["excretion_types"] = tuple(dict.fromkeys(kinds))
    elif record_type == "sleep":
        clocks = tuple(_CLOCK_RE.finditer(clause))
        if clocks:
            normalized_clocks = tuple(
                f"{int(match.group('hour')):02d}:"
                f"{int(match.group('minute') or 0):02d}"
                for match in clocks
            )
            values["bedtime"] = normalized_clocks[0]
            if len(normalized_clocks) > 1:
                values["wake_time"] = normalized_clocks[-1]
        if match := _SLEEP_QUALITY_RE.search(clause):
            values["sleep_quality"] = int(match.group("value"))
        if any(term in clause for term in ("准备开始睡觉", "开始睡觉", "要睡觉")):
            values["sleep_start"] = True
    elif record_type == "goal":
        title = _target_text_after_marker(clause, "目标")
        if title:
            values["titles"] = (title,)
        target_match = re.search(
            r"(?:降到|减到|达到|目标值)(?P<value>\d+(?:\.\d+)?)"
            r"(?P<unit>kg|公斤|千克|斤|cm|厘米|%|次|分钟)?",
            clause,
            re.IGNORECASE,
        )
        if target_match is not None:
            values["target_value"] = float(target_match.group("value"))
            if target_match.group("unit"):
                values["target_unit"] = target_match.group("unit").lower()
    elif record_type == "reminder":
        title = _reminder_target_title(clause)
        if title:
            values["titles"] = (title,)
        clocks = tuple(_CLOCK_RE.finditer(clause))
        if clocks:
            values["times"] = tuple(
                f"{int(match.group('hour')):02d}:"
                f"{int(match.group('minute') or 0):02d}"
                for match in clocks
            )
        if any(term in clause for term in ("每天", "每日")):
            values["recurrence"] = "daily"
    if (
        record_type in {"illness", "symptom"}
        and (severity_match := _SEVERITY_TARGET_RE.search(clause))
    ):
        values["severity"] = int(severity_match.group("value"))
    return values


def _target_text_after_marker(clause: str, marker: str) -> str:
    marker_position = clause.rfind(marker)
    if marker_position < 0:
        return ""
    value = clause[marker_position + len(marker):]
    return value.strip("是为：:，,。.!！；;的 ")


def _target_text_before_marker(clause: str, marker: str) -> str:
    marker_position = clause.rfind(marker)
    if marker_position < 0:
        return ""
    value = clause[:marker_position]
    value = re.sub(
        r"^(?:请|帮我|替我|为我|给我|设置|创建|新增|记录|每天|每日)+",
        "",
        value,
    )
    value = _CLOCK_RE.sub("", value)
    value = re.sub(
        r"^(?:从)?(?:今天|今日|明天|明日|后天)(?:开始|起)?",
        "",
        value,
    )
    value = re.sub(r"^(?:从)?(?:到|至)?(?:每天|每日)?", "", value)
    return value.strip("是为：:，,。.!！；;的 ")


def _reminder_target_title(clause: str) -> str:
    title = _target_text_before_marker(clause, "提醒")
    if title:
        return title
    title = _target_text_after_marker(clause, "提醒")
    title = re.sub(r"^(?:一下)?(?:我|自己)", "", title)
    return title.strip("是为：:，,。.!！；;的 ")


def _diet_meal_food_targets(clause: str) -> dict[str, str]:
    matches: list[tuple[int, int, str]] = []
    for alias, meal_type in _MEAL_TYPE_ALIASES.items():
        if not re.search(r"[\u4e00-\u9fff]", alias):
            continue
        start = clause.find(alias)
        if start >= 0:
            matches.append((start, start + len(alias), meal_type))
    matches.sort()
    targets: dict[str, str] = {}
    for index, (_start, end, meal_type) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(clause)
        food = clause[end:next_start]
        food = food.lstrip("，,：: ")
        food = re.sub(r"^(?:我)?(?:吃了|吃的是|吃|有|是)?", "", food)
        food = re.sub(
            r"(?:然后|再)?(?:请|帮我|替我|为我)?"
            r"(?:记录|记下|保存|录入|写入|打卡)(?:一下)?$",
            "",
            food,
        )
        food = food.strip("和与的了，,。.!！；;：: ")
        if food and food not in {"饮食", "一餐", "饭", "食物"}:
            targets[meal_type] = food[:1000]
    return targets


def _named_item_targets(clause: str, record_type: str) -> tuple[str, ...]:
    if record_type == "medication":
        return tuple(_medication_item_targets(clause))
    action_matches = tuple(_WRITE_TARGET_ACTION_RE.finditer(clause))
    candidate = clause[action_matches[-1].end():] if action_matches else clause
    candidate = re.sub(
        r"^(?:(?:一下|一条|一个|我的|我|今天|今日|已经|刚才|刚刚|"
        r"吃了|服了|服用(?:了)?|用了))+",
        "",
        candidate,
    )
    candidate = re.split(r"(?:，|,|然后|并且|再)", candidate, maxsplit=1)[0]
    candidate = candidate.strip("的了，,。.!！；;：: ")
    if candidate:
        return (candidate,)
    if record_type == "supplement":
        known = tuple(term for term in _SUPPLEMENT_TARGET_TERMS if term in clause)
        return tuple(dict.fromkeys(known))
    return ()


def _looks_like_medication_clause(clause: str) -> bool:
    from app.services.drug_lexicon import contains_medication_reference

    if contains_medication_reference(clause):
        return True
    return any(
        _MEDICATION_NAME_SUFFIX_RE.search(name)
        for name in _medication_item_targets(clause)
    )


def _medication_item_targets(clause: str) -> dict[str, str]:
    return {
        name: details.get("dosage", "")
        for name, details in _medication_item_details(clause).items()
    }


def _medication_item_details(clause: str) -> dict[str, dict[str, str]]:
    action_matches = tuple(_WRITE_TARGET_ACTION_RE.finditer(clause))
    candidate = clause[action_matches[-1].end():] if action_matches else clause
    for _ in range(12):
        stripped = re.sub(
            r"^(?:一下|一条|一个|我的|我|今天|今日|已经|刚才|刚刚|"
            r"吃了|吃的|服了|服用(?:了|的)?|用了|的)",
            "",
            candidate,
        )
        if stripped == candidate:
            break
        candidate = stripped
    candidate = re.split(r"(?:然后|并且|再)", candidate, maxsplit=1)[0]
    targets: dict[str, dict[str, str]] = {}
    for raw_item in re.split(r"[、]|(?:和|与|及)", candidate):
        item = raw_item.strip("的了，,。.!！；;：: ")
        if not item:
            continue
        strength_matches = tuple(_MEDICATION_STRENGTH_RE.finditer(item))
        observed_strength = (
            _canonical_medication_dosage(strength_matches[-1])
            if strength_matches
            else ""
        )
        item_without_strength = _MEDICATION_STRENGTH_RE.sub("", item)
        dose_matches = tuple(_MEDICATION_DOSE_RE.finditer(item_without_strength))
        dosage = _canonical_medication_dosage(dose_matches[0]) if dose_matches else ""
        name = _MEDICATION_DOSE_RE.sub("", item_without_strength)
        name = re.sub(r"^(?:我)?(?:吃了|吃的|服了|服用(?:了|的)?|用了)", "", name)
        name = name.strip("的了，,。.!！；;：: ")
        if name and name not in {"药", "药物", "这次药", "那次药"}:
            targets[name] = {
                "dosage": dosage,
                "observed_strength": observed_strength,
            }
    return targets


def _canonical_medication_dosage(match: re.Match[str]) -> str:
    value = match.group("value")
    value = _CHINESE_DOSE_NUMBERS.get(value, value)
    unit = match.group("unit").lower()
    unit_aliases = {
        "毫克": "mg",
        "克": "g",
        "毫升": "ml",
        "μg": "mcg",
        "ug": "mcg",
    }
    return f"{value}{unit_aliases.get(unit, unit)}"


def _illness_targets(clause: str) -> tuple[str, ...]:
    known = tuple(
        term
        for term in _ILLNESS_TARGET_TERMS
        if term in clause and f"{term}药" not in clause
    )
    if known:
        return tuple(dict.fromkeys(known))

    action_matches = tuple(_WRITE_TARGET_ACTION_RE.finditer(clause))
    candidate = ""
    if action_matches:
        action = action_matches[-1]
        candidate = clause[action.end():]
        candidate = re.sub(
            r"^(?:一下|一条|一个|我的|我|今天|今日|昨天|昨日|以前的|既往)",
            "",
            candidate,
        )
        candidate = re.split(
            r"(?:发作|开始|起病)?(?:日期|时间)(?:是|为)|然后|再分析|再告诉",
            candidate,
            maxsplit=1,
        )[0]
        candidate = candidate.removesuffix("下来")
    if not candidate and action_matches:
        before = clause[:action_matches[-1].start()]
        match = re.search(r"(?:把|将)(?P<target>.+)$", before)
        if match is not None:
            candidate = match.group("target")
    candidate = candidate.strip("的了，,。.!！；;：: ")
    if not candidate or candidate in {"疾病", "不适", "症状", "健康数据", "数据"}:
        return ()
    parts = tuple(
        part.strip()
        for part in re.split(r"[、/]|(?:和|与)", candidate)
        if part.strip()
    )
    if parts and all(_ILLNESS_SUFFIX_RE.search(part) for part in parts):
        return tuple(dict.fromkeys(parts))
    return ()


def _authorization_target_complete(
    record_type: str,
    expected: dict[str, Any],
) -> bool:
    required = {
        "water": ("amount_ml",),
        "weight": ("weight",),
        "blood_pressure": ("systolic", "diastolic"),
        "waist": ("waist_cm",),
        "illness": ("names",),
        "diet": ("meal_types", "food_items"),
        "symptom": ("body_part", "description"),
        "medication": ("names",),
        "supplement": ("names",),
        "exercise": ("exercise_types",),
        "mood": ("mood_score",),
        "excretion": ("excretion_types",),
        "goal": ("titles",),
    }
    if record_type == "diet" and expected.get("meal_food_targets"):
        return True
    if record_type == "diet" and expected.get("attachment_authorized"):
        return True
    if record_type == "mood" and expected.get("mood_values"):
        return True
    if record_type == "sleep" and (
        expected.get("sleep_start")
        or (
            expected.get("bedtime")
            and expected.get("wake_time")
            and expected.get("sleep_quality") is not None
        )
    ):
        return True
    if record_type == "reminder":
        has_title = bool(expected.get("titles")) or bool(
            expected.get("contextual_continuation")
        )
        return has_title and bool(expected.get("times"))
    fields = required.get(record_type)
    if fields is None:
        return False
    return all(expected.get(field) not in (None, "", (), []) for field in fields)


def _target_values_mismatch(
    record_type: str,
    expected: dict[str, Any],
    args: dict[str, Any],
) -> bool:
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    if record_type == "diet":
        requested_meal = _MEAL_TYPE_ALIASES.get(
            str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("meal_type",),
                    arg_keys=("meal_type",),
                )
                or ""
            ).strip().lower(),
            "",
        )
        if expected.get("meal_types"):
            allowed_meals = {
                _MEAL_TYPE_ALIASES.get(
                    str(value).strip().lower(), str(value).strip().lower()
                )
                for value in expected["meal_types"]
            }
            if not requested_meal or requested_meal not in allowed_meals:
                return True
        elif expected.get("attachment_authorized") and not requested_meal:
            return True
        requested_food = _effective_argument_value(
            args,
            data,
            data_keys=("food_items",),
            arg_keys=("food_items",),
        )
        if expected.get("attachment_authorized"):
            if not str(requested_food or "").strip():
                return True
        else:
            meal_food_targets = expected.get("meal_food_targets") or {}
            expected_food = meal_food_targets.get(
                requested_meal,
                expected.get("food_items"),
            )
            if not _food_targets_match(expected_food, requested_food):
                return True

    numeric_keys = {
        "water": (
            ("amount", "amount_ml"),
            ("amount", "amount_ml"),
            expected.get("amount_ml"),
        ),
        "weight": (
            ("weight", "value", "weight_kg"),
            ("weight", "value", "weight_kg", "体重"),
            expected.get("weight"),
        ),
        "blood_pressure": (
            ("systolic",),
            ("systolic",),
            expected.get("systolic"),
        ),
        "waist": (
            ("waist_cm", "waist", "value", "腰围"),
            ("waist_cm", "waist", "value", "腰围"),
            expected.get("waist_cm"),
        ),
    }
    if record_type in numeric_keys:
        data_keys, arg_keys, expected_number = numeric_keys[record_type]
        requested_number = _effective_argument_value(
            args,
            data,
            data_keys=data_keys,
            arg_keys=arg_keys,
        )
        if (
            expected_number is not None
            and (
                requested_number is None
                or not _numbers_match(expected_number, requested_number)
            )
        ):
            return True
    if record_type == "blood_pressure" and expected.get("diastolic") is not None:
        requested_diastolic = _effective_argument_value(
            args,
            data,
            data_keys=("diastolic",),
            arg_keys=("diastolic",),
        )
        if requested_diastolic is None or not _numbers_match(
            expected["diastolic"],
            requested_diastolic,
        ):
            return True
    if record_type == "illness" and expected.get("names"):
        requested_name = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("name", "illness_name"),
                arg_keys=("name", "illness_name"),
            )
            or ""
        ).strip()
        allowed_names = {
            _normalize_entity_name(value) for value in expected["names"]
        }
        if not requested_name or _normalize_entity_name(requested_name) not in allowed_names:
            return True
        requested_status = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("status",),
                arg_keys=("status",),
            )
            or ""
        ).strip().lower()
        expected_status = str(expected.get("status") or "").strip().lower()
        if expected_status:
            if requested_status != expected_status:
                return True
        elif requested_status and requested_status != "active":
            return True
        requested_end_date = _effective_argument_value(
            args,
            data,
            data_keys=("end_date",),
            arg_keys=("end_date",),
        )
        if requested_end_date not in (None, "", []):
            return True
        requested_notes = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("notes",),
                arg_keys=("notes",),
            )
            or ""
        ).strip()
        expected_notes = str(expected.get("notes") or "").strip()
        if expected_notes:
            if _normalize_entity_name(requested_notes) != _normalize_entity_name(
                expected_notes
            ):
                return True
        elif requested_notes:
            return True
    if record_type == "symptom":
        requested_body_part = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("body_part",),
                arg_keys=("body_part",),
            )
            or ""
        ).strip().lower()
        requested_description = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("description",),
                arg_keys=("description",),
            )
            or ""
        ).strip()
        if requested_body_part != str(expected.get("body_part") or "").strip().lower():
            return True
        if not requested_description:
            return True
        expected_description = _normalize_entity_name(expected.get("description"))
        normalized_description = _normalize_entity_name(requested_description)
        if normalized_description not in expected_description and (
            expected_description not in normalized_description
        ):
            return True
        canonical_occurred_at = str(
            expected.get("canonical_occurred_at") or ""
        ).strip()
        if canonical_occurred_at:
            requested_occurred_at = _effective_argument_value(
                args,
                data,
                data_keys=("occurred_at",),
                arg_keys=("occurred_at",),
            )
            if _normalize_clock_value(requested_occurred_at) != str(
                expected.get("occurred_clock") or ""
            ):
                return True
            data.pop("record_date", None)
            data["occurred_at"] = canonical_occurred_at
        else:
            data.pop("occurred_at", None)
            data["record_date"] = str(expected.get("target_date") or "")
        args.pop("occurred_at", None)
        args.pop("record_date", None)
        args.pop("date", None)
    if record_type in {"illness", "symptom"}:
        requested_severity = _effective_argument_value(
            args,
            data,
            data_keys=("severity",),
            arg_keys=("severity",),
        )
        if expected.get("severity") is not None:
            if requested_severity is None or not _numbers_match(
                expected["severity"],
                requested_severity,
            ):
                return True
        elif requested_severity not in (None, "", []):
            # Severity has no safe semantic default.  The model frequently
            # fills the optional schema field with a plausible midpoint even
            # when the user never supplied one.  Project that untrusted field
            # out of the dispatch payload instead of either persisting an
            # invented health fact or rejecting an otherwise exact write.
            data.pop("severity", None)
            args.pop("severity", None)
    if record_type in {"medication", "supplement"}:
        if record_type == "medication":
            name_keys = ("medication_name", "name")
        else:
            name_keys = ("supplement_name", "name")
        requested_name = str(
            _effective_argument_value(
                args,
                data,
                data_keys=name_keys,
                arg_keys=name_keys,
            )
            or ""
        )
        allowed_names = {
            _normalize_entity_name(value) for value in expected.get("names", ())
        }
        normalized_requested_name = _normalize_entity_name(requested_name)
        if normalized_requested_name not in allowed_names:
            return True
        if record_type == "medication":
            expected_dosages = {
                _normalize_entity_name(name): _normalize_medication_dosage(dosage)
                for name, dosage in (expected.get("dosages") or {}).items()
            }
            dosage_values = _medication_actual_dosage_values(args, data)
            normalized_dosage_values = {
                _normalize_medication_dosage(value)
                for value in dosage_values
                if _normalize_medication_dosage(value)
            }
            if len(normalized_dosage_values) > 1:
                return True
            requested_dosage = dosage_values[0] if dosage_values else None
            normalized_requested_dosage = _normalize_medication_dosage(
                requested_dosage
            )
            expected_dosage = expected_dosages.get(normalized_requested_name, "")
            if expected_dosage:
                if normalized_requested_dosage != expected_dosage:
                    return True
            elif normalized_requested_dosage:
                return True
            expected_strengths = {
                _normalize_entity_name(name): _normalize_medication_dosage(strength)
                for name, strength in (
                    expected.get("observed_strengths") or {}
                ).items()
            }
            strength_values = _medication_observed_strength_values(args, data)
            normalized_strength_values = {
                _normalize_medication_dosage(value)
                for value in strength_values
                if _normalize_medication_dosage(value)
            }
            if len(normalized_strength_values) > 1:
                return True
            requested_strength = strength_values[0] if strength_values else None
            normalized_requested_strength = _normalize_medication_dosage(
                requested_strength
            )
            expected_strength = expected_strengths.get(
                normalized_requested_name,
                "",
            )
            if expected_strength:
                if normalized_requested_strength != expected_strength:
                    return True
            elif normalized_requested_strength:
                return True
    if record_type == "exercise":
        requested_exercise = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("exercise_type", "type", "name"),
                arg_keys=("exercise_type", "type", "name"),
            )
            or ""
        )
        allowed_exercises = {
            _normalize_entity_name(value)
            for value in expected.get("exercise_types", ())
        }
        if _normalize_entity_name(requested_exercise) not in allowed_exercises:
            return True
        if expected.get("duration_minutes") is not None:
            requested_duration = _effective_argument_value(
                args,
                data,
                data_keys=("duration", "duration_minutes", "minutes", "分钟"),
                arg_keys=("duration", "duration_minutes", "minutes", "分钟"),
            )
            if requested_duration is None or not _numbers_match(
                expected["duration_minutes"],
                requested_duration,
            ):
                return True
    if record_type == "mood":
        if expected.get("mood_score") is not None:
            requested_score = _effective_argument_value(
                args,
                data,
                data_keys=("mood_score", "score"),
                arg_keys=("mood_score", "score"),
            )
            if requested_score is None or not _numbers_match(
                expected["mood_score"],
                requested_score,
            ):
                return True
        elif expected.get("mood_values"):
            requested_mood = str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("mood", "status", "mood_label"),
                    arg_keys=("mood", "status", "mood_label"),
                )
                or ""
            ).strip().lower()
            allowed_moods = {
                _MOOD_TARGET_ALIASES.get(str(value).strip().lower(), "")
                for value in expected["mood_values"]
            }
            if _MOOD_TARGET_ALIASES.get(requested_mood, "") not in allowed_moods:
                return True
    if record_type == "excretion":
        requested_type = str(
            _effective_argument_value(
                args,
                data,
                data_keys=("type", "excretion_type"),
                arg_keys=("type", "excretion_type"),
            )
            or ""
        ).strip().lower()
        allowed_types = {
            _EXCRETION_TARGET_ALIASES.get(str(value).strip().lower(), "")
            for value in expected.get("excretion_types", ())
        }
        if _EXCRETION_TARGET_ALIASES.get(requested_type, "") not in allowed_types:
            return True
    if record_type == "sleep":
        if expected.get("bedtime"):
            requested_bedtime = _effective_argument_value(
                args,
                data,
                data_keys=("bedtime",),
                arg_keys=("bedtime",),
            )
            if _normalize_clock_value(requested_bedtime) != expected["bedtime"]:
                return True
        if expected.get("wake_time"):
            requested_wake_time = _effective_argument_value(
                args,
                data,
                data_keys=("wake_time",),
                arg_keys=("wake_time",),
            )
            if _normalize_clock_value(requested_wake_time) != expected["wake_time"]:
                return True
        if expected.get("sleep_quality") is not None:
            requested_quality = _effective_argument_value(
                args,
                data,
                data_keys=("sleep_quality", "quality"),
                arg_keys=("sleep_quality", "quality"),
            )
            if requested_quality is None or not _numbers_match(
                expected["sleep_quality"],
                requested_quality,
            ):
                return True
    if record_type == "goal":
        requested_title = _effective_argument_value(
            args,
            data,
            data_keys=("title",),
            arg_keys=("title",),
        )
        allowed_titles = {
            _normalize_entity_name(value) for value in expected.get("titles", ())
        }
        if _normalize_entity_name(requested_title) not in allowed_titles:
            return True
        if expected.get("target_value") is not None:
            requested_target = _effective_argument_value(
                args,
                data,
                data_keys=("target_value",),
                arg_keys=("target_value",),
            )
            if requested_target is None or not _numbers_match(
                expected["target_value"],
                requested_target,
            ):
                return True
        if expected.get("target_unit"):
            requested_unit = _effective_argument_value(
                args,
                data,
                data_keys=("target_unit",),
                arg_keys=("target_unit",),
            )
            if _normalize_unit(requested_unit) != _normalize_unit(
                expected["target_unit"]
            ):
                return True
    if record_type == "reminder":
        if expected.get("titles"):
            requested_title = _effective_argument_value(
                args,
                data,
                data_keys=("title",),
                arg_keys=("title",),
            )
            allowed_titles = {
                _normalize_reminder_title(value) for value in expected["titles"]
            }
            if _normalize_reminder_title(requested_title) not in allowed_titles:
                return True
        requested_times = tuple(
            clock
            for clock in (
                _normalize_clock_value(
                    _effective_argument_value(
                        args,
                        data,
                        data_keys=(key,),
                        arg_keys=(key,),
                    )
                )
                for key in ("time", "remind_at", "start_time", "end_time")
            )
            if clock
        )
        if set(requested_times) != set(expected.get("times", ())):
            return True
        if expected.get("recurrence"):
            requested_recurrence = str(
                _effective_argument_value(
                    args,
                    data,
                    data_keys=("recurrence",),
                    arg_keys=("recurrence",),
                )
                or ""
            ).strip().lower()
            if requested_recurrence != expected["recurrence"]:
                return True

    skip_default_recurring_date = (
        record_type == "reminder"
        and bool(expected.get("recurrence"))
        and str(expected.get("target_date") or "")
        == str(expected.get("default_date") or "")
    )
    if not skip_default_recurring_date:
        requested_date = _effective_record_date(record_type, args, data)
        effective_date = requested_date or str(expected.get("default_date") or "")
        if str(expected.get("target_date") or "") != effective_date:
            return True
    return False


def _medication_actual_dosage_values(
    args: dict[str, Any],
    data: dict[str, Any],
) -> tuple[Any, ...]:
    values, _strengths = _medication_alias_values(args, data)
    return values


def _medication_observed_strength_values(
    args: dict[str, Any],
    data: dict[str, Any],
) -> tuple[Any, ...]:
    _actual, values = _medication_alias_values(args, data)
    return values


def _effective_argument_value(
    args: dict[str, Any],
    data: dict[str, Any],
    *,
    data_keys: tuple[str, ...],
    arg_keys: tuple[str, ...],
) -> Any:
    for container, keys in ((data, data_keys), (args, arg_keys)):
        for key in keys:
            if key in container and container[key] is not None:
                return container[key]
    return None


def _effective_record_date(
    record_type: str,
    args: dict[str, Any],
    data: dict[str, Any],
) -> str:
    if record_type == "illness":
        value = _effective_argument_value(
            args,
            data,
            data_keys=("start_date",),
            arg_keys=(),
        )
    elif record_type == "symptom":
        value = _effective_argument_value(
            args,
            data,
            data_keys=("occurred_at", "record_date"),
            arg_keys=(),
        )
    elif record_type == "reminder":
        value = _effective_argument_value(
            args,
            data,
            data_keys=("remind_at",),
            arg_keys=(),
        )
    else:
        value = _effective_argument_value(
            args,
            data,
            data_keys=("record_date",),
            arg_keys=(),
        )
    return str(value or "").strip()[:10]


def _normalize_entity_name(value: Any) -> str:
    return re.sub(r"[\s,，、。.!！;；:：]+", "", str(value or "")).casefold()


def _normalize_medication_dosage(value: Any) -> str:
    text = str(value or "").strip()
    match = _MEDICATION_DOSE_RE.fullmatch(text)
    if match is None:
        return _normalize_entity_name(text)
    return _canonical_medication_dosage(match)


def _normalize_clock_value(value: Any) -> str:
    match = _CLOCK_RE.search(str(value or ""))
    if match is None:
        return ""
    return (
        f"{int(match.group('hour')):02d}:"
        f"{int(match.group('minute') or 0):02d}"
    )


def _normalize_unit(value: Any) -> str:
    aliases = {
        "厘米": "cm",
        "公斤": "kg",
        "千克": "kg",
    }
    normalized = str(value or "").strip().lower()
    return aliases.get(normalized, normalized)


def _normalize_reminder_title(value: Any) -> str:
    normalized = _normalize_entity_name(value)
    return re.sub(r"(?:提醒|闹钟)$", "", normalized)


def _food_targets_match(expected: Any, requested: Any) -> bool:
    def split_text(value: Any) -> list[str]:
        raw_parts: list[str] = []
        for punct_part in re.split(r"[,，、;；/|+＋]", str(value or "")):
            # Protect lexical ``和牛`` before splitting conjunctions.  This
            # distinguishes ``米饭和和牛`` (two foods) from ``米饭和牛`` (one
            # malformed/other entity) and avoids collapsing both into 牛.
            placeholder = "\uf8ffWAGYU\uf8ff"
            protected = punct_part.replace("和牛", placeholder)
            raw_parts.extend(
                part.replace(placeholder, "和牛")
                for part in re.split(r"(?<=.)[和与及](?=.)", protected)
            )
        return raw_parts

    def parts(value: Any) -> tuple[str, ...]:
        if isinstance(value, (list, tuple)):
            raw_parts = []
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("food_name")
                    quantity = item.get("quantity")
                    unit = item.get("unit")
                    if name and quantity is not None and unit:
                        raw_parts.append(f"{name}{quantity}{unit}")
                    elif name:
                        raw_parts.append(str(name))
                    continue
                raw_parts.extend(split_text(item))
        else:
            raw_parts = split_text(value)
        return tuple(
            sorted(
                _canonical_food_part(part)
                for part in raw_parts
                if _canonical_food_part(part)
            )
        )

    return bool(parts(expected)) and parts(expected) == parts(requested)


def _canonical_food_part(value: Any) -> str:
    part = _normalize_entity_name(value)
    if not part:
        return ""
    quantity = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百半]+)"
    unit = r"(?:毫升|ml|克|g|碗|杯|份|个|只|枚|颗|片|块|根|条)"
    leading = re.fullmatch(
        rf"(?P<number>{quantity})(?P<unit>{unit})(?P<food>.+)",
        part,
        re.IGNORECASE,
    )
    trailing = re.fullmatch(
        rf"(?P<food>.+?)(?P<number>{quantity})(?P<unit>{unit})",
        part,
        re.IGNORECASE,
    )
    match = leading or trailing
    if match is None:
        return part
    unit_aliases = {"只": "个", "枚": "个", "颗": "个"}
    normalized_number = _CHINESE_DOSE_NUMBERS.get(
        match.group("number"),
        match.group("number"),
    )
    return (
        f"{match.group('food')}#{normalized_number}"
        f"{unit_aliases.get(match.group('unit'), match.group('unit'))}"
    ).casefold()


def _numbers_match(expected: Any, requested: Any) -> bool:
    try:
        return abs(float(expected) - float(requested)) < 1e-6
    except (TypeError, ValueError):
        return str(expected).strip() == str(requested).strip()
