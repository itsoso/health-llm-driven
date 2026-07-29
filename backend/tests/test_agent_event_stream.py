from app.services.agent_kernel.context import build_turn_snapshot
from app.services.agent_kernel.events import AgentEventBus
from app.services.agent_kernel.types import ToolExecutionRequest


def test_agent_event_bus_emits_traceable_tool_and_receipt_events(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    snapshot = build_turn_snapshot(
        db,
        user_id=user.id,
        channel="typed",
        text="记录午餐吃了牛肉面",
        run_id="run-42",
        turn_id="turn-42",
    )
    bus = AgentEventBus(snapshot)

    bus.turn_started()
    bus.intent_decided()
    bus.tool_requested(ToolExecutionRequest(tool_name="health_record", arguments={}))
    bus.capability_decided(tool_name="health_record", action="allow", reason="explicit_create_intent")
    bus.tool_result(
        tool_name="health_record",
        success=True,
        receipt={"operation_id": "health_record:7", "resource_id": "7"},
    )
    bus.turn_ended(status="complete")

    assert [event.name for event in bus.events] == [
        "agent.turn_start",
        "agent.intent_decided",
        "agent.tool_requested",
        "agent.capability_decided",
        "agent.tool_allowed",
        "agent.tool_result",
        "agent.write_receipt_verified",
        "agent.turn_end",
    ]
    for event in bus.events:
        assert event.run_id == "run-42"
        assert event.turn_id == "turn-42"
        assert event.user_id == user.id
        assert event.channel == "typed"

    summary = bus.trace_summary(status="complete")
    assert summary["run_id"] == "run-42"
    assert summary["turn_id"] == "turn-42"
    assert summary["status"] == "complete"
    assert summary["event_counts"]["agent.tool_requested"] == 1
    assert summary["tool_requests"] == 1
    assert summary["tool_results"] == 1
    assert summary["verified_receipts"] == 1
    assert summary["blocked_tools"] == 0


def test_agent_event_summary_exposes_goal_progress_without_health_content(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    snapshot = build_turn_snapshot(
        db,
        user_id=user.id,
        channel="typed",
        text="重新估算和写入早午两餐",
        run_id="run-goal",
        turn_id="turn-goal",
    )
    bus = AgentEventBus(snapshot)

    bus.goal_evaluated(
        satisfied=False,
        verified_target_count=1,
        reason="verification_targets_missing",
    )
    summary = bus.trace_summary(status="incomplete")

    assert summary["goal_kind"] == "diet_recalculate_update"
    assert summary["goal_target_count"] == 2
    assert summary["goal_verified_target_count"] == 1
    assert summary["goal_satisfied"] is False
    assert summary["goal_reason"] == "verification_targets_missing"
    assert "breakfast" not in repr(summary)
    assert "lunch" not in repr(summary)
