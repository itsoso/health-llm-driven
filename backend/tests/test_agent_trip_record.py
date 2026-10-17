"""Current-turn trip facts must survive authorization without invented details."""

import json

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext


TRIP = "记录我的行程，我现在在口岸，准备去海岛，走的是跨海大桥。"
FACTS = "我现在在口岸，准备去海岛，走的是跨海大桥"


async def execute_trip(db, monkeypatch, message):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "typed"
    executor._current_turn_user_message = message
    executor._current_turn_recent_messages = [
        {"role": "assistant", "content": "上一餐摄入约500千卡。"},
    ]
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.types import TurnSnapshot

    envelope = AgentEnvelope(user_id=1, channel="typed", text=message)
    context = ExecutionContext.for_test(user_id=1, channel="typed")
    executor._agent_kernel_snapshot = TurnSnapshot(
        envelope=envelope, context=context,
        intent=build_intent_frame(envelope, context), policy_mode="enforce",
    )
    calls = []

    async def post(url, headers, payload):
        calls.append((url, headers, payload))
        return '{"id": 92, "record_id": 92, "status": "recorded"}'

    monkeypatch.setattr(executor, "_api_post", post)
    result = await executor._execute_tool("health_record", {
        "record_type": "event",
        "data": {"title": "已到达海岛", "notes": "模型补充", "user_id": 999,
                 "occurred_at": "2030-01-01T00:00:00+08:00"},
    }, "test-token")
    return calls, result


@pytest.mark.asyncio
async def test_current_turn_trip_projects_only_explicit_facts(db, monkeypatch):
    calls, result = await execute_trip(db, monkeypatch, TRIP)
    assert len(calls) == 1
    assert calls[0][0].endswith("/episodes/life-event")
    assert calls[0][1]["Authorization"] == "Bearer test-token"
    assert calls[0][2] == {"title": "我现在在口岸", "notes": FACTS}
    assert json.loads(result)["id"] == 92


@pytest.mark.asyncio
@pytest.mark.parametrize("message", (
    "不要" + TRIP,
    TRIP + "先别记录。",
    "朋友说：" + TRIP,
    "如果" + TRIP,
    "解释这句话：“" + TRIP + "”",
    TRIP.replace("我的行程", "朋友的行程"),
    TRIP.replace("我现在", "小明现在"),
    TRIP + "这是小明的行程。",
    TRIP.replace("。", "吗？"),
))
async def test_trip_denials_and_other_owners_never_post(db, monkeypatch, message):
    calls, _ = await execute_trip(db, monkeypatch, message)
    assert calls == []


@pytest.mark.asyncio
async def test_stream_trip_persists_owned_event_and_receipt(
    db, client, auth_user_and_headers, monkeypatch,
):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.episode import HealthEpisode

    user, headers = auth_user_and_headers
    conversation = AgentConversation(user_id=user.id, title="测试行程", session_key="trip-test")
    db.add(conversation)
    db.flush()
    db.add(AgentMessage(conversation_id=conversation.id, role="assistant",
                        content="上一餐摄入约500千卡。"))
    db.commit()
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    llm_calls = 0

    async def model_stream(messages, tools):
        nonlocal llm_calls
        llm_calls += 1
        if llm_calls == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "trip-write", "function": {
                    "name": "health_record",
                    "arguments": json.dumps({"record_type": "event", "data": {
                        "title": "已经到达海岛", "user_id": user.id + 1,
                        "notes": "未经用户提供的内容",
                    }}),
                },
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "行程已记录。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def post(url, request_headers, payload):
        assert request_headers["Authorization"] == headers["Authorization"]
        response = client.post("/api/v1/episodes/life-event", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        return response.text

    monkeypatch.setattr(executor, "_call_llm_stream", model_stream)
    monkeypatch.setattr(executor, "_api_post", post)
    events = [event async for event in executor.run_stream(
        user_id=user.id, message=TRIP, conversation_id=conversation.id,
        user_auth_token=headers["Authorization"].removeprefix("Bearer "),
        client_turn_id="test-current-trip",
    )]
    rows = db.query(HealthEpisode).filter_by(episode_type="life_event").all()
    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert rows[0].headline == "我现在在口岸"
    assert rows[0].context_snapshot["notes"] == FACTS
    done = next(event["data"] for event in events if event.get("event") == "done")
    assert done["write_receipts"]
    assert done["write_receipts"][0]["verified"] is True
    saved = db.get(AgentMessage, done["message_id"])
    assert saved.meta["write_receipts"] == done["write_receipts"]
