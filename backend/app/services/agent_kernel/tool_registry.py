"""Immutable execution metadata for every Agent tool.

Provider schemas stay in ``tool_schema_registry``. This module owns the
operational contract used after a tool call has been selected: effect class,
dispatch adapter, timeout and receipt requirements.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from app.services.specialist_tools import SPECIALIST_TOOLS


ToolEffect = Literal["read", "write", "mixed"]
ResolvedToolEffect = Literal["read", "write"]
AdapterKind = Literal["executor", "specialist"]
ExecutorCallStyle = Literal["http", "args"]


class ToolRegistryError(RuntimeError):
    """Base class for fail-closed tool metadata errors."""


class UnknownTool(ToolRegistryError):
    pass


class UnknownToolAction(ToolRegistryError):
    pass


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    effect: ToolEffect
    executor_method: str | None
    timeout_seconds: float = 90.0
    receipt_required: bool = False
    adapter_kind: AdapterKind = "executor"
    call_style: ExecutorCallStyle = "http"
    action_field: str | None = None
    read_actions: frozenset[str] = frozenset()
    write_actions: frozenset[str] = frozenset()
    receipt_exempt_record_types: frozenset[str] = frozenset()
    annotate_implausible: bool = False
    marks_deep_analysis: bool = False

    def classify_effect(self, arguments: Any) -> ResolvedToolEffect:
        args = _parse_arguments(arguments)
        action = str(args.get(self.action_field or "") or "").strip().lower()
        if self.effect != "mixed":
            if self.action_field and action not in self.read_actions | self.write_actions:
                raise UnknownToolAction(
                    f"unknown_tool_action:{self.name}:{action or 'missing'}"
                )
            return self.effect
        if action in self.read_actions:
            return "read"
        if action in self.write_actions:
            return "write"
        raise UnknownToolAction(f"unknown_tool_action:{self.name}:{action or 'missing'}")

    def requires_verified_receipt(self, arguments: Any) -> bool:
        if not self.receipt_required or self.classify_effect(arguments) != "write":
            return False
        if self.name != "health_record" or not self.receipt_exempt_record_types:
            return True
        args = _parse_arguments(arguments)
        record_type = str(
            args.get("record_type") or args.get("type") or ""
        ).strip().lower()
        return record_type not in self.receipt_exempt_record_types


def _spec(
    name: str,
    effect: ToolEffect,
    executor_method: str,
    **kwargs: Any,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        effect=effect,
        executor_method=executor_method,
        **kwargs,
    )


_CORE_TOOL_SPECS = (
    _spec(
        "health_query",
        "read",
        "_exec_health_query",
        annotate_implausible=True,
    ),
    _spec("health_query_batch", "read", "_exec_health_query_batch"),
    _spec(
        "health_record",
        "write",
        "_exec_health_record",
        receipt_required=True,
        receipt_exempt_record_types=frozenset({"garmin_sync"}),
    ),
    _spec(
        "health_manage",
        "mixed",
        "_exec_health_manage",
        receipt_required=True,
        action_field="operation",
        read_actions=frozenset({"list"}),
        write_actions=frozenset({"update", "delete"}),
    ),
    _spec(
        "health_analysis",
        "read",
        "_exec_health_analysis",
        timeout_seconds=135.0,
        annotate_implausible=True,
        marks_deep_analysis=True,
    ),
    _spec("environment_check", "read", "_exec_environment"),
    _spec("supplement_guide", "read", "_exec_supplement_guide"),
    _spec(
        "upload_genetic_txt",
        "write",
        "_exec_upload_genetic_txt",
        receipt_required=True,
    ),
    _spec("query_genetic_profile", "read", "_exec_query_genetic_profile"),
    _spec(
        "upload_medical_exam_text",
        "write",
        "_exec_upload_medical_exam_text",
        receipt_required=True,
    ),
    _spec(
        "query_lab_indicators",
        "read",
        "_exec_query_lab_indicators",
        annotate_implausible=True,
    ),
    _spec(
        "intervention_cycle",
        "mixed",
        "_exec_intervention_cycle",
        receipt_required=True,
        call_style="args",
        action_field="action",
        read_actions=frozenset({"status", "list", "history"}),
        write_actions=frozenset({"start", "update", "cancel", "delete"}),
    ),
    _spec(
        "knowledge_search",
        "read",
        "_exec_knowledge_search",
        call_style="args",
    ),
    _spec(
        "realtime_search",
        "read",
        "_exec_realtime_search",
        call_style="args",
    ),
    _spec(
        "manage_plan",
        "write",
        "_exec_manage_plan",
        receipt_required=True,
        action_field="action",
        write_actions=frozenset(
            {"generate_weekly", "complete_item", "save_to_card"}
        ),
    ),
    _spec(
        "draft_aigc_media",
        "write",
        "_exec_draft_aigc_media",
        receipt_required=True,
        call_style="args",
    ),
)

_SPECIALIST_TOOL_SPECS = tuple(
    ToolSpec(
        name=name,
        effect="read",
        executor_method=None,
        adapter_kind="specialist",
    )
    for name in SPECIALIST_TOOLS
)

_TOOL_SPECS: Mapping[str, ToolSpec] = {
    spec.name: spec for spec in (*_CORE_TOOL_SPECS, *_SPECIALIST_TOOL_SPECS)
}


def list_tool_specs() -> tuple[ToolSpec, ...]:
    return tuple(_TOOL_SPECS.values())


def get_tool_spec(tool_name: str) -> ToolSpec:
    normalized = str(tool_name or "").strip()
    try:
        return _TOOL_SPECS[normalized]
    except KeyError as exc:
        raise UnknownTool(f"unknown_tool:{normalized or 'missing'}") from exc


def classify_tool_effect(tool_name: str, arguments: Any) -> ResolvedToolEffect:
    return get_tool_spec(tool_name).classify_effect(arguments)


def requires_verified_receipt(tool_name: str, arguments: Any) -> bool:
    return get_tool_spec(tool_name).requires_verified_receipt(arguments)


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    try:
        return dict(raw or {})
    except (TypeError, ValueError):
        return {}
