"""Owned Garmin sync imperatives must not grant broader ingestion authority."""

from dataclasses import replace

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    ToolExecutionRequest,
    TurnSnapshot,
)


def _snapshot(text):
    envelope = AgentEnvelope(user_id=1, channel="chat", text=text)
    context = ExecutionContext.for_test(user_id=1, channel="chat")
    return TurnSnapshot(
        envelope=envelope,
        context=context,
        intent=build_intent_frame(envelope, context),
    )


def _decide(text, data=None):
    return decide_tool_capability(
        _snapshot(text),
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "garmin_sync", "data": {} if data is None else data},
            source="structured",
        ),
    )


@pytest.mark.parametrize("text", [
    "同步佳明的数据。",
    "请帮我同步一下我的 Garmin 数据",
    "获取佳明的数据，同步一下，主动触发一下同步。",
    "获取佳明的数据，同步一下。",
    "请获取我的Garmin数据，帮我同步一下。",
    "同步佳明的数据，主动触发一下同步。",
    # Repeated wording still grants only one effect; real Pi deduplication is
    # covered by test_sync_intent_frame_scope's repeated-command trajectory.
    "获取佳明的数据，同步一下，同步一下，同步一下。",
])
def test_explicit_owned_sync_imperative_is_authorized(text):
    decision = _decide(text)
    assert decision.action == "allow", decision.reason
    assert decision.reason == "explicit_owned_garmin_sync"
    assert decision.normalized_args == {"record_type": "garmin_sync", "data": {}}


@pytest.mark.parametrize("text", [
    "获取佳明的数据。",
    "佳明的数据同步完了吗？",
    "获取佳明的数据，同步一下了吗？",
    "昨晚睡得怎样，佳明的数据同步完了吗？",
    "获取我妈妈的佳明数据，同步一下。",
    "获取朋友的佳明数据，同步一下，主动触发一下同步。",
    "获取佳明昨天的数据，同步一下。",
    "获取佳明的数据，同步一下昨天的数据。",
    "获取佳明的数据，不要同步。",
    "不要获取佳明的数据，同步一下。",
    "获取佳明的数据，同步一下，算了不要同步。",
    "只查看：获取佳明的数据，同步一下。",
    "如果我同意，获取佳明的数据，同步一下。",
    "解释一下“获取佳明的数据，同步一下”。",
    "“获取佳明的数据，同步一下。”",
    '"获取佳明的数据，同步一下。"',
    "```获取佳明的数据，同步一下。```",
    "朋友说：获取佳明的数据，同步一下。",
    "获取佳明的数据，同步一下，然后删除全部数据。",
    "明天获取佳明的数据，同步一下。",
])
def test_non_authorizing_sync_scope_is_blocked(text):
    assert _decide(text).action == "block"


@pytest.mark.parametrize("data", [{"user_id": 2}, {"date": "2026-09-01"}, {"days": 30}])
def test_owned_sync_cannot_supply_target_or_date_arguments(data):
    assert _decide("获取佳明的数据，同步一下，主动触发一下同步。", data).action == "block"


def test_readonly_intent_cannot_be_promoted_by_sync_policy():
    snapshot = _snapshot("获取佳明的数据，同步一下，主动触发一下同步。")
    snapshot = replace(snapshot, intent=replace(snapshot.intent, primary="query", operation="query", is_write=False))
    decision = decide_tool_capability(snapshot, ToolExecutionRequest(
        tool_name="health_record", arguments={"record_type": "garmin_sync", "data": {}}, source="structured",
    ))
    assert decision.action == "block"
