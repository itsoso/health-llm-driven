from __future__ import annotations

import pytest


def test_registry_covers_every_core_and_specialist_tool_exactly_once():
    from app.services.agent_kernel.tool_registry import list_tool_specs
    from app.services.specialist_tools import SPECIALIST_TOOLS
    from app.services.tool_schema_registry import get_tool_names

    specs = list_tool_specs()
    names = [spec.name for spec in specs]

    assert len(names) == len(set(names))
    assert set(names) == set(get_tool_names()) | set(SPECIALIST_TOOLS)


@pytest.mark.parametrize(
    ("tool_name", "args", "expected"),
    [
        ("health_query", {"dimension": "sleep"}, "read"),
        ("health_manage", {"operation": "list"}, "read"),
        ("health_manage", {"operation": "update"}, "write"),
        ("health_manage", {"operation": "delete"}, "write"),
        ("intervention_cycle", {"action": "status"}, "read"),
        ("intervention_cycle", {"action": "history"}, "read"),
        ("intervention_cycle", {"action": "start"}, "write"),
        ("health_record", {"record_type": "diet"}, "write"),
        ("analyze_recovery", {}, "read"),
    ],
)
def test_tool_effect_is_deterministic(tool_name, args, expected):
    from app.services.agent_kernel.tool_registry import classify_tool_effect

    assert classify_tool_effect(tool_name, args) == expected


@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("health_manage", {"operation": "archive"}),
        ("intervention_cycle", {"action": "resume_unknown"}),
    ],
)
def test_unknown_mixed_action_fails_closed(tool_name, args):
    from app.services.agent_kernel.tool_registry import UnknownToolAction

    with pytest.raises(UnknownToolAction):
        from app.services.agent_kernel.tool_registry import classify_tool_effect

        classify_tool_effect(tool_name, args)


def test_receipt_requirement_is_derived_from_spec_and_arguments():
    from app.services.agent_kernel.tool_registry import requires_verified_receipt

    assert requires_verified_receipt("health_record", {"record_type": "diet"}) is True
    assert (
        requires_verified_receipt(
            "health_record", {"record_type": "garmin_sync"}
        )
        is False
    )
    assert requires_verified_receipt("health_manage", {"operation": "list"}) is False
    assert requires_verified_receipt("health_manage", {"operation": "delete"}) is True
    assert requires_verified_receipt("health_query", {"dimension": "diet"}) is False


def test_specs_preserve_existing_adapter_and_timeout_contracts():
    from app.services.agent_kernel.tool_registry import get_tool_spec

    health_query = get_tool_spec("health_query")
    analysis = get_tool_spec("health_analysis")
    specialist = get_tool_spec("analyze_recovery")

    assert health_query.executor_method == "_exec_health_query"
    assert health_query.timeout_seconds == 90.0
    assert health_query.annotate_implausible is True
    assert analysis.timeout_seconds == 135.0
    assert analysis.marks_deep_analysis is True
    assert specialist.adapter_kind == "specialist"
    assert specialist.executor_method is None


def test_unknown_tool_fails_closed():
    from app.services.agent_kernel.tool_registry import UnknownTool

    with pytest.raises(UnknownTool):
        from app.services.agent_kernel.tool_registry import get_tool_spec

        get_tool_spec("future_unregistered_tool")
