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
    TRIP.replace("口岸", "口岸（上述内容仅为示例）"),
    TRIP.replace("口岸", "口岸（仅为举例）"),
    TRIP.replace("口岸", "口岸（此为假设）"),
    TRIP.replace("跨海大桥", "跨海大桥这个说法不代表授权"),
    TRIP.replace("口岸", "口岸上述内容仅为示例"),
    TRIP.replace("海岛", "海岛这只是虚构故事"),
    "记录我的行程，我现在在口岸此为假定",
    "记录我的行程，我现在在口岸这段话是小明说的",
    "记录我的行程，我现在在口岸暂时不要存",
    "记录我的行程，我现在在口岸这是尚未识别的附言",
    "记录我的行程，我现在在口岸，准备去海岛这是附言",
    "记录我的行程，我现在在口岸，走的是大桥这是附言",
))
async def test_trip_denials_and_other_owners_never_post(db, monkeypatch, message):
    calls, _ = await execute_trip(db, monkeypatch, message)
    assert calls == []


def test_trip_projection_preserves_place_spelling():
    from app.services.write_intent_scope import current_turn_trip_payload

    assert current_turn_trip_payload("记录我的行程，我目前在Harbor Bay口岸，计划去New Town市。") == {
        "title": "我目前在Harbor Bay口岸",
        "notes": "我目前在Harbor Bay口岸，计划去New Town市",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("message,expected_title,expected_notes", (
    (TRIP, "我现在在口岸", FACTS),
    ("记录行程现在到了上海国际机场", "现在到了上海国际机场", "现在到了上海国际机场"),
    ("记录我的行程，现在到了上海国际机场。", "现在到了上海国际机场", "现在到了上海国际机场"),
    ("到家了。记录下来。", "到家了", "到家了"),
    ("我到家了，帮我记一下。", "我到家了", "我到家了"),
))
async def test_stream_trip_persists_owned_event_and_receipt(
    db, client, auth_user_and_headers, monkeypatch, message, expected_title, expected_notes,
):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.episode import HealthEpisode

    user, headers = auth_user_and_headers
    conversation = AgentConversation(user_id=user.id, title="测试行程", session_key="trip-test")
    db.add(conversation)
    db.flush()
    db.add(AgentMessage(conversation_id=conversation.id, role="assistant",
                        content="上一餐摄入约500千卡。"))
    if "到家" in message:
        db.add(AgentMessage(conversation_id=conversation.id, role="user",
                            content="到了18号门 20:40 降落"))
        db.add(AgentMessage(conversation_id=conversation.id, role="assistant",
                            content="本轮数据查询未完成，请明确数据类别和日期。"))
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
        user_id=user.id, message=message, conversation_id=conversation.id,
        user_auth_token=headers["Authorization"].removeprefix("Bearer "),
        client_turn_id="test-current-trip",
    )]
    rows = db.query(HealthEpisode).filter_by(episode_type="life_event").all()
    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert rows[0].headline == expected_title
    assert rows[0].context_snapshot["notes"] == expected_notes
    # The existing API anchors an undated current event to request time.
    # A clock from previous chat/model output must never become its raw time.
    assert rows[0].context_snapshot["occurred_raw"] is None
    done = next(event["data"] for event in events if event.get("event") == "done")
    assert done["write_receipts"]
    assert done["write_receipts"][0]["verified"] is True
    saved = db.get(AgentMessage, done["message_id"])
    assert saved.meta["write_receipts"] == done["write_receipts"]
    assert done["completion_status"] == done["turn_outcome"]["status"] == "complete"
    assert "剂量" not in saved.content and "查询未完成" not in saved.content

    replay = [e async for e in executor.run_stream(
        user_id=user.id, message=message, conversation_id=conversation.id,
        user_auth_token=headers["Authorization"].removeprefix("Bearer "),
        client_turn_id="test-current-trip",
    )]
    replay_done = next(e["data"] for e in replay if e.get("event") == "done")
    assert replay_done["message_id"] == done["message_id"]
    assert db.query(HealthEpisode).filter_by(episode_type="life_event").count() == 1

    from tests.conftest import create_authenticated_user
    _, other_token = create_authenticated_user(db)
    owned_read = client.get("/api/v1/episodes/me/life-events", headers=headers)
    assert owned_read.status_code == 200
    assert [row["id"] for row in owned_read.json()] == [rows[0].id]
    other_read = client.get("/api/v1/episodes/me/life-events",
                            headers={"Authorization": f"Bearer {other_token}"})
    assert other_read.status_code == 200 and other_read.json() == []

    # A subsequent location assertion closes as context, not a health query
    # or another write. Exercise actual persisted receipt metadata above.
    def unexpected(*args, **kwargs):
        pytest.fail("Completed trip context must not invoke health data/model work")
    monkeypatch.setattr(executor, "_build_system_prompt", unexpected)
    if "到家" in message:
        return  # The earlier query failure is deliberately unresolved history.
    followup = [e async for e in executor.run_stream(user_id=user.id,
        message="现在到了北京国际机场", conversation_id=conversation.id,
        client_turn_id="test-trip-arrival-context")]
    followup_done = next(e["data"] for e in followup if e.get("event") == "done")
    assert followup_done["route"] == "context_statement"
    assert followup_done["completion_status"] == "complete"
    assert db.query(HealthEpisode).filter_by(episode_type="life_event").count() == 1
