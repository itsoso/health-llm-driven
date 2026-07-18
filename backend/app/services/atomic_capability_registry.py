"""Agent Native AtomicCapability registry.

DynamicView composers may only emit card types registered here. The registry is
intentionally deterministic: LLMs can choose and rank capabilities, but they do
not invent card schemas, action types, write endpoints, or safety boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping
from urllib.parse import quote


@dataclass(frozen=True)
class AtomicCapability:
    id: str
    version: str
    card_type: str
    first_class_objects: tuple[str, ...]
    surfaces: tuple[str, ...]
    data_required_fields: tuple[str, ...]
    action_types: tuple[str, ...]
    safety_boundary: str
    telemetry_events: tuple[str, ...]
    execution: str


CAPABILITIES: tuple[AtomicCapability, ...] = (
    AtomicCapability(
        id="daily_artifact",
        version="v1",
        card_type="daily_artifact",
        first_class_objects=("HealthTwin", "HealthAgendaItem", "InterventionCycle"),
        surfaces=("mobile.today", "mobile.chat"),
        data_required_fields=("artifact_date", "generated_by", "top_action", "safety_boundary"),
        action_types=(),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "accepted", "completed", "skipped"),
        execution="manual_confirm_write_via_agenda_or_daily_artifact_event",
    ),
    AtomicCapability(
        id="runtime_agenda",
        version="v1",
        card_type="runtime_agenda",
        first_class_objects=("HealthAgendaItem", "InterventionCycle"),
        surfaces=("mobile.today", "mobile.chat", "watch.summary"),
        data_required_fields=("mode", "generated_by", "start", "end", "next_action", "days"),
        action_types=("route.open", "agenda.complete", "daily_plan_action.complete"),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "open", "dismiss"),
        execution="manual_confirm_complete_or_route_open",
    ),
    AtomicCapability(
        # R4 安全地板卡:SafetyGuardian CRITICAL/HIGH 告警钉在 Today 视图 hero 之上。
        # data 形状 = agent_executor._safety_alert_card_descriptor(mobile SafetyCard 契约)。
        # 唯一允许的动作是 route.open 到安全告警页 —— 安全卡永不携带写路径。
        id="safety",
        version="v1",
        card_type="safety",
        first_class_objects=("HealthTwin",),
        surfaces=("mobile.today", "mobile.chat"),
        data_required_fields=(
            "title",
            "severity",
            "summary",
            "recommendations",
            "boundary",
            "requires_medical_attention",
        ),
        action_types=("route.open",),
        safety_boundary="alert_non_diagnostic",
        telemetry_events=("impression", "open"),
        execution="read_only_route_open",
    ),
    AtomicCapability(
        # 汇总类卡结构化 v1:今日饮食汇总(餐次记录 + 宏量合计 + 确定性派生观察 + 饮水)。
        # data 形状 = genui.diet_summary.build_diet_daily_summary 的 descriptor.data,
        # 与 mobile DietSummaryCard 契约对齐。观察确定性派生(factual、非诊断,R4);
        # 唯一动作是 route.open(查看详细数据/明日计划)—— 只读,永不携带写路径。
        id="diet_daily_summary",
        version="v1",
        card_type="diet_daily_summary",
        first_class_objects=("DietRecord",),
        surfaces=("mobile.chat",),
        data_required_fields=("record_date", "meals", "totals"),
        action_types=("route.open",),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "open"),
        execution="read_only_route_open",
    ),
    AtomicCapability(
        # 汇总类卡结构化 v1:睡眠概览(逐夜评分/时长/深睡 + 均值 + 时长目标 + 确定性观察)。
        # data 形状 = genui.sleep_summary.build_sleep_summary 的 descriptor.data,与 mobile
        # SleepSummaryCard 契约对齐。观察确定性派生(factual、非诊断,R4;绝不消费服务端
        # quality_assessment);唯一动作是 route.open(查看睡眠详情)—— 只读,永不携带写路径。
        id="sleep_summary",
        version="v1",
        card_type="sleep_summary",
        first_class_objects=("HealthTwin",),
        surfaces=("mobile.chat",),
        data_required_fields=("range_label", "nights", "averages"),
        action_types=("route.open",),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "open"),
        execution="read_only_route_open",
    ),
    AtomicCapability(
        id="diet_draft",
        version="v1",
        card_type="diet_draft",
        first_class_objects=("DietRecord",),
        surfaces=("mobile.chat", "web.chat", "mac.chat"),
        data_required_fields=("meal_type", "food_items"),
        action_types=("diet_record.create", "ui.inline.expand", "route.open"),
        safety_boundary="manual_confirm_write",
        telemetry_events=("impression", "confirm", "write_receipt", "open"),
        execution="manual_confirm_diet_record_create",
    ),
    AtomicCapability(
        id="medication_draft",
        version="v1",
        card_type="medication_draft",
        first_class_objects=("Medication", "MedicationLog"),
        surfaces=("mobile.chat", "web.chat", "mac.chat"),
        data_required_fields=("medication_name",),
        action_types=("route.open",),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "open"),
        execution="read_only_route_open",
    ),
    AtomicCapability(
        id="supplement_draft",
        version="v1",
        card_type="supplement_draft",
        first_class_objects=("SupplementDefinition", "SupplementRecord"),
        surfaces=("mobile.chat", "web.chat", "mac.chat"),
        data_required_fields=("supplement_name",),
        action_types=("route.open",),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "open"),
        execution="read_only_route_open",
    ),
    AtomicCapability(
        id="operating_review",
        version="v1",
        card_type="operating_review",
        first_class_objects=("HealthTwin", "HealthAgendaItem", "InterventionCycle"),
        surfaces=("mobile.chat", "web.chat", "mac.chat"),
        data_required_fields=("window_days", "execution"),
        action_types=("route.open",),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "open"),
        execution="read_only_route_open",
    ),
    AtomicCapability(
        id="metric_chart",
        version="v1",
        card_type="metric_chart",
        first_class_objects=("HealthTwin",),
        surfaces=("mobile.chat", "web.chat", "mac.chat"),
        data_required_fields=("metric",),
        action_types=("route.open",),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "open"),
        execution="read_only_route_open",
    ),
    AtomicCapability(
        # 草稿只暴露一条手动确认动作。客户端不携带 prompt/source/provider
        # 参数，后端只消费 owner-scoped 的一次性确认记录。
        id="aigc_media_confirmation",
        version="v1",
        card_type="aigc_media_confirmation",
        first_class_objects=("AIGCMediaConfirmation",),
        surfaces=("mobile.chat", "web.chat", "mac.chat"),
        data_required_fields=("confirmation_id", "kind", "status", "title", "provider", "source_attached"),
        action_types=("aigc_media.confirm",),
        safety_boundary="manual_owner_confirmation_for_external_provider",
        telemetry_events=("impression", "manual_confirm", "provider_dispatch"),
        execution="owner_scoped_one_time_confirmation",
    ),
    AtomicCapability(
        # AIGC 结果只作为 owner-scoped 任务投影显示；卡片不持久化签名 URL。
        id="aigc_media_job",
        version="v1",
        card_type="aigc_media_job",
        first_class_objects=("AIGCMediaJob",),
        surfaces=("mobile.chat", "web.chat", "mac.chat"),
        data_required_fields=("job_id", "kind", "status", "progress", "title", "result"),
        action_types=(),
        safety_boundary="owner_scoped_private_media",
        telemetry_events=("impression", "status_refresh", "result_open"),
        execution="read_only_private_job_projection",
    ),
)

_CAPABILITY_BY_CARD_TYPE = {capability.card_type: capability for capability in CAPABILITIES}
_WRITE_ACTION_TYPES = frozenset({
    "agenda.complete",
    "daily_plan_action.complete",
    "diet_record.create",
    "write_intent.confirm",
    "write_intent.dismiss",
    "aigc_media.confirm",
})


def get_atomic_capability(card_type: str) -> AtomicCapability | None:
    return _CAPABILITY_BY_CARD_TYPE.get(str(card_type or "").strip())


def attach_action_policy_metadata(
    card_type: str,
    actions: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach the registered capability policy to each executable action."""
    capability = get_atomic_capability(card_type)
    if capability is None:
        raise ValueError(f"unknown card capability: {card_type}")
    allowed_actions = set(capability.action_types)
    output: list[dict[str, Any]] = []
    for action in actions:
        action_type = str(action.get("action") or "").strip()
        if action_type not in allowed_actions:
            raise ValueError(
                f"action {action_type!r} is not registered for card type {card_type!r}"
            )
        is_write = action_type in _WRITE_ACTION_TYPES
        output.append({
            **dict(action),
            "capability_id": f"{capability.id}.{capability.version}",
            "required_receipt": is_write,
            "autonomy_tier": "manual_confirm" if is_write else "suggest",
            "policy_reason": "manual_confirm_write" if is_write else "registered_read_action",
        })
    return output


def validate_dynamic_view(view: Mapping[str, Any]) -> list[str]:
    """Return capability contract violations for a DynamicView payload."""
    violations: list[str] = []
    surface = str(view.get("surface") or "").strip()
    sections = view.get("sections")
    if not isinstance(sections, list):
        return ["sections: expected list"]

    for section_index, section in enumerate(sections):
        section_path = f"sections[{section_index}]"
        if not isinstance(section, Mapping):
            violations.append(f"{section_path}: expected object")
            continue
        cards = section.get("cards")
        if not isinstance(cards, list):
            violations.append(f"{section_path}.cards: expected list")
            continue
        for card_index, card in enumerate(cards):
            card_path = f"{section_path}.cards[{card_index}]"
            violations.extend(_validate_card(card, card_path, surface))

    return violations


def _validate_card(card: Any, card_path: str, surface: str) -> list[str]:
    violations: list[str] = []
    if not isinstance(card, Mapping):
        return [f"{card_path}: expected object"]

    card_type = str(card.get("type") or "").strip()
    capability = get_atomic_capability(card_type)
    if capability is None:
        return [f"{card_path}: unknown AtomicCapability card type '{card_type}'"]

    if surface and surface not in capability.surfaces:
        violations.append(f"{card_path}: {card_type} is not registered for surface '{surface}'")

    data = card.get("data")
    if not isinstance(data, Mapping):
        violations.append(f"{card_path}: {card_type} data must be an object")
    else:
        for field in capability.data_required_fields:
            if field not in data:
                violations.append(f"{card_path}: {card_type} data missing required field '{field}'")

    actions = card.get("actions")
    if actions is not None:
        if not isinstance(actions, list):
            violations.append(f"{card_path}.actions: expected list")
        else:
            violations.extend(_validate_actions(actions, capability, card_path))

    return violations


def _validate_actions(
    actions: list[Any],
    capability: AtomicCapability,
    card_path: str,
) -> list[str]:
    violations: list[str] = []
    allowed = set(capability.action_types)
    for action_index, action in enumerate(actions):
        action_path = f"{card_path}.actions[{action_index}]"
        if not isinstance(action, Mapping):
            violations.append(f"{action_path}: expected object")
            continue
        action_type = str(action.get("action") or "").strip()
        if action_type not in allowed:
            violations.append(
                f"{action_path}: action '{action_type}' is not allowed for {capability.card_type}"
            )
            continue
        is_write = action_type in _WRITE_ACTION_TYPES
        expected_capability_id = f"{capability.id}.{capability.version}"
        if action.get("capability_id") != expected_capability_id:
            violations.append(f"{action_path}: action capability_id does not match {expected_capability_id}")
        if action.get("required_receipt") is not is_write:
            violations.append(f"{action_path}: action required_receipt does not match capability policy")
        if action.get("autonomy_tier") != ("manual_confirm" if is_write else "suggest"):
            violations.append(f"{action_path}: action autonomy_tier does not match capability policy")
        if action.get("policy_reason") != ("manual_confirm_write" if is_write else "registered_read_action"):
            violations.append(f"{action_path}: action policy_reason does not match capability policy")
        if is_write:
            if action.get("requires_manual_confirm") is not True:
                violations.append(f"{action_path}: write action requires manual confirmation")
                continue
        if action_type == "agenda.complete" and action.get("endpoint") != "/agenda/complete":
            violations.append(f"{action_path}: agenda.complete endpoint is not allowed")
        if action_type == "daily_plan_action.complete":
            payload = action.get("payload") if isinstance(action.get("payload"), Mapping) else {}
            action_id = str(payload.get("action_id") or "").strip()
            endpoint = str(action.get("endpoint") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", action_id):
                violations.append(f"{action_path}: invalid daily plan action id")
            elif endpoint != f"/daily-plan/actions/{quote(action_id, safe='._-')}/events":
                violations.append(f"{action_path}: daily plan completion endpoint does not match payload")
    return violations
