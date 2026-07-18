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
