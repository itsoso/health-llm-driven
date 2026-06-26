"""Backend-owned Health Agenda contract.

This module centralizes the cross-surface vocabulary for Agenda projections.
It is intentionally small and additive: storage still uses source tables plus
the HealthEvent agenda lifecycle, while clients can rely on this contract for
status, event, source, and surface semantics.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


CONTRACT_VERSION = "health_agenda_contract_v1"


class AgendaItemStatus(str, Enum):
    PENDING = "pending"
    DUE = "due"
    OVERDUE = "overdue"
    INFO = "info"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    SNOOZED = "snoozed"
    ADJUSTED = "adjusted"
    AUTO_OBSERVED = "auto_observed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ExecutionEventStatus(str, Enum):
    DONE = "done"
    SKIPPED = "skipped"
    SNOOZED = "snoozed"
    ADJUSTED = "adjusted"
    AUTO_OBSERVED = "auto_observed"
    CONFIRMED = "confirmed"
    FAILED = "failed"


ITEM_STATUSES = tuple(status.value for status in AgendaItemStatus)
EXECUTION_EVENT_STATUSES = tuple(status.value for status in ExecutionEventStatus)

_STATUS_ALIASES = {
    "done": AgendaItemStatus.COMPLETED.value,
    "verified": AgendaItemStatus.COMPLETED.value,
    "scheduled": AgendaItemStatus.PENDING.value,
    "failed": AgendaItemStatus.BLOCKED.value,
}

TERMINAL_ITEM_STATUSES = frozenset({
    AgendaItemStatus.COMPLETED.value,
    AgendaItemStatus.SKIPPED.value,
    AgendaItemStatus.AUTO_OBSERVED.value,
    AgendaItemStatus.EXPIRED.value,
    AgendaItemStatus.CANCELLED.value,
    AgendaItemStatus.BLOCKED.value,
})

ACTIONABLE_ITEM_STATUSES = frozenset({
    AgendaItemStatus.PENDING.value,
    AgendaItemStatus.DUE.value,
    AgendaItemStatus.OVERDUE.value,
})

_EXECUTION_TO_ITEM_STATUS = {
    ExecutionEventStatus.DONE.value: AgendaItemStatus.COMPLETED.value,
    ExecutionEventStatus.SKIPPED.value: AgendaItemStatus.SKIPPED.value,
    ExecutionEventStatus.SNOOZED.value: AgendaItemStatus.SNOOZED.value,
    ExecutionEventStatus.ADJUSTED.value: AgendaItemStatus.ADJUSTED.value,
    ExecutionEventStatus.AUTO_OBSERVED.value: AgendaItemStatus.AUTO_OBSERVED.value,
    ExecutionEventStatus.CONFIRMED.value: AgendaItemStatus.COMPLETED.value,
    ExecutionEventStatus.FAILED.value: AgendaItemStatus.BLOCKED.value,
}

HEALTH_EVENT_AGENDA_STATUS_TO_ITEM_STATUS = {
    "pending": AgendaItemStatus.PENDING.value,
    "done": AgendaItemStatus.COMPLETED.value,
    "skipped": AgendaItemStatus.SKIPPED.value,
    "expired": AgendaItemStatus.EXPIRED.value,
}

KNOWN_SOURCE_OBJECT_TYPES = frozenset({
    "action_card",
    "daily_plan_action",
    "data_quality",
    "day_schedule_workout",
    "health_problem",
    "health_protocol",
    "intervention_cycle",
    "measurement",
    "medication",
    "outcome_correction",
    "reminder",
    "review_schedule",
    "safety_alert",
    "supplement",
    "training_decision",
    "training_plan",
    "write_intent",
})

SURFACES = ("watch", "mobile", "mac", "web", "rokid", "external_agent")


def canonical_item_status(status: Any) -> str:
    """Return the canonical HealthAgendaItem status for a legacy/current value."""
    text = str(status or AgendaItemStatus.PENDING.value).strip().lower()
    if not text:
        return AgendaItemStatus.PENDING.value
    return _STATUS_ALIASES.get(text, text)


def execution_event_to_item_status(status: Any) -> str:
    """Map client-facing execution event status to item lifecycle status."""
    text = str(status or "").strip().lower()
    if text not in _EXECUTION_TO_ITEM_STATUS:
        raise ValueError(f"unsupported execution event status: {text}")
    return _EXECUTION_TO_ITEM_STATUS[text]


def is_terminal_item_status(status: Any) -> bool:
    return canonical_item_status(status) in TERMINAL_ITEM_STATUSES


def is_actionable_item_status(status: Any) -> bool:
    return canonical_item_status(status) in ACTIONABLE_ITEM_STATUSES


def source_ref(object_type: str, object_id: Any) -> dict[str, Any]:
    return {"object_type": str(object_type), "object_id": object_id}


def is_known_source_ref(source: Mapping[str, Any] | None) -> bool:
    if not isinstance(source, Mapping):
        return False
    object_type = str(source.get("object_type") or "")
    return object_type in KNOWN_SOURCE_OBJECT_TYPES


def surface_contract_for_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return the primary and alternate surfaces for an agenda item."""
    typ = str(item.get("type") or "")
    raw_source = item.get("source")
    source = raw_source if isinstance(raw_source, Mapping) else {}
    source_type = str(source.get("object_type") or "")

    if typ in {"movement", "training", "exercise", "activity"}:
        return {"primary": "watch", "alternates": ["mobile", "rokid"]}
    if typ in {"nutrition", "diet", "food"}:
        return {"primary": "mobile", "alternates": ["rokid", "watch"]}
    if typ in {"hydration", "medication", "supplement", "sleep", "recovery"}:
        return {"primary": "watch", "alternates": ["mobile"]}
    if typ in {"checkup", "lab_recheck", "doctor"} or source_type in {
        "health_problem",
        "review_schedule",
    }:
        return {"primary": "mobile", "alternates": ["mac", "watch"]}
    return {"primary": "mobile", "alternates": ["watch"]}


def contract_metadata_for_item(item: Mapping[str, Any]) -> dict[str, Any]:
    status = canonical_item_status(item.get("status"))
    source = item.get("source")
    return {
        "version": CONTRACT_VERSION,
        "item_statuses": list(ITEM_STATUSES),
        "execution_event_statuses": list(EXECUTION_EVENT_STATUSES),
        "source_known": is_known_source_ref(source if isinstance(source, Mapping) else None),
        "source_object_type": (
            source.get("object_type") if isinstance(source, Mapping) else None
        ),
        "status": status,
    }
