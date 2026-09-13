"""Repair feedback cannot grant authority or dispatch rejected parameters."""

import json
from types import SimpleNamespace

import pytest

from app.services.agent_policy_retry import (
    READ_REPAIR_REASONS,
    is_terminal_policy_reason,
    terminal_policy_notice,
)
from app.services.agent_kernel.tool_gateway import ToolGateway, blocked_tool_result
from app.services.agent_kernel.types import CapabilityDecision, ToolExecutionRequest

HARD_REASONS = (
    "health_query_subject_not_current_user",
    "health_query_not_requested",
    "health_query_cancelled_by_user",
    "explicit_write_cancellation",
    "explicit_aigc_media_provider_veto",
    "recipe_replay_tool_not_allowed",
    "recipe_replay_record_type_not_allowed",
    "telegram_directive_tool_not_allowed",
)


@pytest.mark.parametrize("reason", sorted(READ_REPAIR_REASONS))
@pytest.mark.parametrize(
    "tool,args",
    [
        ("health_query", {"dimension": "sleep"}),
        ("health_query_batch", {"queries": []}),
        ("health_manage", {"record_type": "diet", "operation": "list"}),
    ],
)
def test_read_parameter_feedback_is_rejected_but_repairable(reason, tool, args):
    payload = json.loads(
        blocked_tool_result(CapabilityDecision("block", reason, tool, args))
    )
    assert payload["status"] == "rejected" and payload["success"] is False
    assert payload["dispatch_started"] is False
    assert payload["retryable"] is True and payload["terminal"] is False
    assert payload["error_category"] == "read_parameters"
    assert payload["recovery_guidance"]
    assert (
        "原话" in payload["recovery_guidance"] or "本轮" in payload["recovery_guidance"]
    )
    assert not is_terminal_policy_reason(reason)


@pytest.mark.parametrize(
    "tool,args",
    [
        ("health_record", {"record_type": "supplement"}),
        ("health_manage", {"record_type": "diet", "operation": "update"}),
        ("user_directive", {}),
        ("invented_reader", {}),
    ],
)
def test_read_reason_on_a_write_or_unknown_tool_cannot_advertise_retry(tool, args):
    payload = json.loads(
        blocked_tool_result(
            CapabilityDecision("block", "health_query_semantics_unresolved", tool, args)
        )
    )
    assert payload["retryable"] is False
    assert payload["dispatch_started"] is False


@pytest.mark.parametrize("reason", HARD_REASONS)
def test_hard_permission_or_cancellation_feedback_requires_stop(reason):
    payload = json.loads(
        blocked_tool_result(CapabilityDecision("block", reason, "health_query", {}))
    )
    assert payload["retryable"] is False and payload["terminal"] is True
    assert payload["success"] is False
    assert payload["error_category"] in {"permission_denied", "cancelled"}
    assert (
        "重试" not in payload["recovery_guidance"]
        or "不要" in payload["recovery_guidance"]
    )
    assert is_terminal_policy_reason(reason)
    notice = terminal_policy_notice([reason], has_verified_writes=True)
    assert notice and "已核实保存" in notice


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "shadow"])
@pytest.mark.parametrize("reason", HARD_REASONS + tuple(sorted(READ_REPAIR_REASONS)))
async def test_rejected_hard_or_read_parameters_never_cross_dispatch(
    monkeypatch, mode, reason
):
    gateway = ToolGateway(SimpleNamespace(policy_mode=mode))
    decision = CapabilityDecision("block", reason, "health_query", {})
    monkeypatch.setattr(gateway, "preflight", lambda request: decision)
    dispatched = []

    async def dispatch(request):
        dispatched.append(request)
        return "must not execute"

    result = await gateway.execute(ToolExecutionRequest("health_query", {}), dispatch)
    assert not dispatched
    payload = json.loads(result.content)
    assert payload["status"] == "rejected" and payload["dispatch_started"] is False


def test_feedback_never_echoes_argument_values_or_adds_fake_result():
    payload = json.loads(
        blocked_tool_result(
            CapabilityDecision(
                "block",
                "health_query_calendar_window_conflict",
                "health_query",
                {"secret_health_value": "PRIVATE", "credential": "TOKEN"},
            )
        )
    )
    assert "PRIVATE" not in json.dumps(payload) and "TOKEN" not in json.dumps(payload)
    assert "records" not in payload and "data" not in payload
