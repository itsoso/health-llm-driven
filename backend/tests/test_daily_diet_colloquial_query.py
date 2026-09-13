"""A dated colloquial diet question must reach the same owned read as 饮食."""
from datetime import datetime
import json

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import (
    AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot,
)


def snapshot(message):
    envelope = AgentEnvelope(user_id=41, channel="typed", text=message)
    context = ExecutionContext(
        user_id=41, channel="typed", timezone="Asia/Shanghai",
        current_time=datetime.fromisoformat("2026-09-12T17:21:00+00:00"),
    )
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "今天我吃的怎么样?", "今天我吃得怎么样？", "我今天吃得怎么样",
    "今天吃得如何", "今日我吃的怎样？", "今天我吃的怎么样？给我一些建议。",
])
@pytest.mark.parametrize("tool,args", [
    ("health_query", {"dimension": "diet", "days": 30}),
    ("health_manage", {"record_type": "diet", "operation": "list"}),
])
async def test_colloquial_diet_question_dispatches_only_business_today(message, tool, args):
    calls = []

    async def dispatch(request):
        calls.append((request.tool_name, request.arguments))
        return '{"records": [], "count": 0}'

    await ToolGateway(snapshot(message)).execute(ToolExecutionRequest(tool, args), dispatch)
    assert calls == [("health_query", {
        "dimension": "diet", "start_date": "2026-09-13",
        "end_date": "2026-09-13", "timezone": "Asia/Shanghai",
    })]


@pytest.mark.parametrize("message", [
    "今天妈妈吃得怎么样", "假如我问今天我吃得怎么样", "分析以下例句：今天我吃得怎么样",
    "不要查询今天我吃得怎么样", "今天我应该怎么吃", "明天我吃得怎么样",
    "昨天和今天我吃得怎么样", "今天我吃的药怎么样", "今天我吃的补剂怎么样",
    "今天我吃得怎么样，然后删除今天饮食",
])
def test_colloquial_grammar_does_not_expand_read_authority(message):
    decision = decide_tool_capability(snapshot(message), ToolExecutionRequest(
        "health_query", {"dimension": "diet"}))
    assert decision.action == "block"


@pytest.mark.parametrize("args", [
    {"dimension": "diet", "start_date": "2026-09-12", "end_date": "2026-09-12"},
    {"dimension": "sleep"}, {"dimension": "genetic"},
])
def test_model_cannot_change_colloquial_query_scope(args):
    assert decide_tool_capability(snapshot("今天我吃的怎么样？"),
        ToolExecutionRequest("health_query", args)).action == "block"


@pytest.mark.parametrize("message,expected_date", [
    ("昨天我吃得怎么样", "2026-09-12"),
    ("2026年9月10日我吃的怎么样", "2026-09-10"),
])
def test_colloquial_past_day_stays_on_requested_date(message, expected_date):
    decision = decide_tool_capability(snapshot(message), ToolExecutionRequest(
        "health_query", {"dimension": "diet", "days": 30}))
    assert decision.action == "allow"
    assert decision.normalized_args == {
        "dimension": "diet", "start_date": expected_date,
        "end_date": expected_date, "timezone": "Asia/Shanghai",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
async def test_original_question_completes_through_pi(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel,
):
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    rounds = []

    async def provider(messages, tools):
        rounds.append(messages)
        if len(rounds) == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "diet-read", "type": "function", "function": {
                    "name": "health_query", "arguments": '{"dimension":"diet","days":1}',
                },
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "已查询今天的饮食，没有可用记录，暂时无法评价。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def dispatch(request, token):
        calls.append(request)
        return '{"records": [], "count": 0, "availability": "no_data"}'

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Use tools.")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    events = [event async for event in executor.run_stream(
        user.id, "今天我吃的怎么样?", client_turn_id="colloquial-diet",
        extra_context=json.dumps({"multi_model": panel}),
    )]
    assert len(calls) == 1
    assert calls[0].arguments["dimension"] == "diet"
    assert calls[0].arguments["start_date"] == calls[0].arguments["end_date"]
    assert calls[0].arguments["timezone"] == "Asia/Shanghai"
    assert events[-1]["data"]["turn_outcome"]["status"] == "complete"


@pytest.mark.asyncio
async def test_original_question_reads_only_owned_day_postgres(db, auth_user_and_headers):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated TEST_DATABASE_URL PostgreSQL")
    from dataclasses import replace
    from datetime import date
    from app.models.daily_health import DietRecord
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor

    owner, _ = auth_user_and_headers
    other = User(username="colloquial-other", name="Synthetic other", hashed_password="fixture")
    db.add(other)
    db.flush()
    for uid, day, label in [
        (owner.id, 12, "previous-day"), (owner.id, 13, "owned-today"),
        (other.id, 13, "other-owner"),
    ]:
        db.add(DietRecord(user_id=uid, record_date=date(2026, 9, day),
                          meal_type="午餐", food_name=label))
    db.commit()
    snap = snapshot("今天我吃的怎么样?")
    snap = replace(snap, envelope=replace(snap.envelope, user_id=owner.id),
                   context=replace(snap.context, user_id=owner.id))
    decision = decide_tool_capability(snap, ToolExecutionRequest(
        "health_query", {"dimension": "diet", "days": 1}))
    assert decision.action == "allow"
    executor = AgentExecutor(db)
    executor._current_user_id = owner.id
    executor._current_turn_user_message = snap.envelope.text
    executor._agent_kernel_snapshot = snap
    result = json.loads(await executor._exec_health_query("http://unused", {}, decision.normalized_args))
    assert [record["food_name"] for record in result["records"]] == ["owned-today"]
    assert result["window"] == {
        "start_date": "2026-09-13", "end_date": "2026-09-13", "timezone": "Asia/Shanghai",
    }
    assert db.query(DietRecord).count() == 3
