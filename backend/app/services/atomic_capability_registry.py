"""Agent Native AtomicCapability registry.

DynamicView composers may only emit card types registered here. The registry is
intentionally deterministic: LLMs can choose and rank capabilities, but they do
not invent card schemas, action types, write endpoints, or safety boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


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
        action_types=("route.open",),
        safety_boundary="suggest_only",
        telemetry_events=("impression", "open", "dismiss"),
        execution="read_only_route_open",
    ),
)

_CAPABILITY_BY_CARD_TYPE = {capability.card_type: capability for capability in CAPABILITIES}


def get_atomic_capability(card_type: str) -> AtomicCapability | None:
    return _CAPABILITY_BY_CARD_TYPE.get(str(card_type or "").strip())


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
    return violations
