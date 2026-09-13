"""Pi feedback batches, not sibling calls, consume the bounded read repair budget."""

import copy
import json
from uuid import uuid4

import pytest

from app.models.agent_conversation import AgentMessage
from app.models.daily_health import WorkoutRecord
from app.models.supplement import SupplementDefinition, SupplementRecord
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock,
    owned_data as owned_data,
    script_executor,
)


QUERY = (
    "我的既往诊断是几个月前的事情。请基于诊断时间判断当前状况，"
    "结合我每天实际服用的补剂、睡眠、运动、情绪、工作和饮食，先调用工具查询已有记录，再给建议。"
)
DIMENSIONS = ("diet", "sleep", "workout", "supplements")
QUERIES = [{"dimension": dimension, "days": 7} for dimension in DIMENSIONS]
BAD = [
    ("health_query", {"dimension": "hrv", "days": 7}),
    ("health_query", {"dimension": "sleep", "days": 1}),
]
GOOD = [("health_query_batch", {"queries": QUERIES})]
ANSWER = "本轮依据实际查到的记录回答，未覆盖的信息仍然未知。"


@pytest.fixture
def four_domain_user(db, owned_data, clock):
    definition = SupplementDefinition(user_id=owned_data.id, name="Synthetic repair", is_active=False)
    db.add(definition)
    db.flush()
    db.add_all([
        WorkoutRecord(user_id=owned_data.id, workout_date=clock[0].date(),
                      workout_name="Synthetic walk", workout_type="walking",
                      duration_seconds=1200, source="synthetic"),
        SupplementRecord(user_id=owned_data.id, supplement_id=definition.id,
                         record_date=clock[0].date(), taken=True),
    ])
    db.commit()
    return owned_data


def batch_trace(db, monkeypatch, steps):
    trace = script_executor(db, monkeypatch, [])
    trace.steps = steps

    def response(messages, tools):
        index = len(trace.calls)
        trace.calls.append(copy.deepcopy((messages, tools)))
        assert index < len(steps), "No unplanned model retries"
        step = steps[index]
        if isinstance(step, str):
            return {"content": step, "finish_reason": "stop"}
        return {"content": "", "finish_reason": "tool_calls", "tool_calls": [
            {"id": f"repair-{index}-{i}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}
            for i, (name, args) in enumerate(step)
        ]}

    async def stream(messages, tools):
        reply = response(messages, tools)
        if reply.get("tool_calls"):
            yield {"type": "tool_calls", "tool_calls": reply["tool_calls"]}
        else:
            yield {"type": "content", "text": reply["content"]}
        yield {"type": "finish", "finish_reason": reply["finish_reason"]}

    async def lead(messages, tools):
        return response(messages, tools)

    class PanelProvider:
        async def chat(self, **kwargs):
            assert not kwargs.get("tools")
            return {"content": ANSWER, "finish_reason": "stop"}

    monkeypatch.setattr(trace.executor, "_call_llm_stream", stream)
    monkeypatch.setattr(trace.executor, "_call_llm", lead)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *a, **k: PanelProvider())
    return trace


async def consume(db, trace, user, *, panel=False, query=QUERY):
    stream = trace.executor.run_stream(
        user.id, query, channel="typed", client_turn_id=str(uuid4()),
        extra_context=json.dumps({"multi_model": panel}),
    )
    events = [event async for event in stream]
    done = next(event["data"] for event in reversed(events) if event.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    if panel:
        assert done["mode"] == "multi_model"
    assert saved.meta["turn_outcome"] == done["turn_outcome"]
    assert "".join(event["data"].get("content", "") for event in events if event.get("event") == "token") == saved.content
    assert not done["write_receipts"]
    return done, saved


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("prior_failed_batch", [False, True])
async def test_sibling_parameter_errors_do_not_preempt_correct_four_domain_read(
    db, four_domain_user, monkeypatch, panel, prior_failed_batch,
):
    steps = ([BAD] if prior_failed_batch else []) + [[*BAD, *GOOD], ANSWER]
    trace = batch_trace(db, monkeypatch, steps)
    done, saved = await consume(db, trace, four_domain_user, panel=panel)
    assert len(trace.dispatches) == 1
    assert trace.dispatches[0].tool_name == "health_query_batch"
    for query in trace.dispatches[0].arguments["queries"]:
        assert query == {"dimension": query["dimension"], "days": 7,
                         "start_date": "2026-09-07", "end_date": "2026-09-13", "timezone": "Asia/Shanghai"}
    assert {goal["goal_id"]: goal["status"] for goal in done["turn_outcome"]["goals"]} == {
        dimension: "verified" for dimension in DIMENSIONS
    }
    assert done["turn_outcome"]["status"] == "complete"
    assert ANSWER in saved.content
    assert all(tools for _, tools in trace.calls[:-1])
    from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
    from app.services.agent_composed_read_completion import read_scope_notices

    scope = resolve_owned_read_scope(trace.executor._agent_kernel_snapshot)
    first_system = trace.calls[0][0][0]["content"]
    assert json.dumps(list(scope.queries), ensure_ascii=False) in first_system
    assert all(notice in first_system for notice in read_scope_notices(scope))


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
async def test_two_unsuccessful_feedback_batches_stop_and_next_user_turn_resets(
    db, four_domain_user, monkeypatch, panel,
):
    trace = batch_trace(db, monkeypatch, [BAD, BAD, ANSWER])
    done, _ = await consume(db, trace, four_domain_user, panel=panel)
    assert trace.calls[0][1] and trace.calls[1][1]
    assert not trace.calls[2][1]
    assert trace.executor._read_repair_failures == 2
    assert not trace.dispatches
    assert done["turn_outcome"]["status"] != "complete"
    assert all(goal["status"] == "failed" for goal in done["turn_outcome"]["goals"])
    trace.steps.extend([GOOD, ANSWER])
    done, _ = await consume(db, trace, four_domain_user, panel=panel)
    assert trace.calls[3][1]
    assert len(trace.dispatches) == 1
    assert done["turn_outcome"]["status"] == "complete"
    assert trace.executor._read_repair_failures == 0


@pytest.mark.asyncio
async def test_partial_read_does_not_complete_or_authorize_an_unrequested_dimension(
    db, four_domain_user, monkeypatch,
):
    trace = batch_trace(db, monkeypatch, [[*BAD, ("health_query", QUERIES[0])], ANSWER])
    done, saved = await consume(db, trace, four_domain_user)
    assert [request.arguments["dimension"] for request in trace.dispatches] == ["diet"]
    assert done["turn_outcome"]["status"] == "partial"
    goals = {goal["goal_id"]: goal["status"] for goal in done["turn_outcome"]["goals"]}
    assert goals == {dimension: "verified" if dimension == "diet" else "failed" for dimension in DIMENSIONS}
    assert "饮食：已记录1条" in saved.content and "200千卡" in saved.content


@pytest.mark.asyncio
@pytest.mark.parametrize("query,args", [
    (QUERY, {"dimension": "sleep", "days": 7, "user_id": 999999}),
    ("不要查询我的睡眠记录", {"dimension": "sleep", "days": 7}),
])
async def test_terminal_permission_or_cancellation_cannot_be_cleared_by_parameter_failure(
    db, auth_user_and_headers, monkeypatch, query, args,
):
    from unittest.mock import AsyncMock
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = query
    executor._turn_channel = "typed"
    executor._start_agent_kernel_turn(user_id=user.id, message=query, channel="typed")
    executor._begin_read_repair_batch()
    dispatch = AsyncMock(side_effect=AssertionError("Denied scope must not dispatch"))
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    await executor._execute_tool("health_query", args, None)
    assert executor._force_no_tools_synthesis
    await executor._execute_tool("health_query", {"dimension": "hrv", "days": 7}, None)
    assert executor._force_no_tools_synthesis
    executor._settle_read_repair_batch()
    assert executor._force_no_tools_synthesis
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_read_repair_batch_cannot_grant_a_health_write(db, auth_user_and_headers, monkeypatch):
    from unittest.mock import AsyncMock
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_write_outcome import result_declares_explicit_failure

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = QUERY
    executor._turn_channel = "typed"
    executor._start_agent_kernel_turn(user_id=user.id, message=QUERY, channel="typed")
    executor._begin_read_repair_batch()
    dispatch = AsyncMock(side_effect=AssertionError("Read repair cannot grant writes"))
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    for name, args in BAD:
        await executor._execute_tool(name, args, None)
    result = await executor._execute_tool(
        "health_record", {"record_type": "water", "data": {"amount": 200}}, None,
    )
    assert result_declares_explicit_failure(result) or result.startswith("Error:")
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_production_tool_facade_without_model_batch_retains_bounded_direct_attempts(
    db, four_domain_user, monkeypatch,
):
    from app.config import settings
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

    monkeypatch.setattr(settings, "agent_runtime_mode", "off")
    executor = AgentExecutor(db)
    facade = CloudAgentRuntimeFacade(db)
    results = []
    for name, args in [*BAD, *GOOD]:
        result = await facade.execute_tool(
            user_id=four_domain_user.id, message=QUERY, origin="voice_command", channel="typed",
            tool_name=name, arguments=args, client_turn_id=str(uuid4()), executor=executor,
        )
        results.append(json.loads(result))
    assert results[-1]["error_code"] == "read_repair_budget_exhausted"
    assert results[-1]["dispatch_started"] is False
    assert executor._read_repair_failures == 2


@pytest.mark.asyncio
async def test_provider_ignoring_exhausted_tool_list_still_cannot_dispatch(
    db, four_domain_user, monkeypatch,
):
    trace = batch_trace(db, monkeypatch, [BAD, BAD, GOOD])
    done, _ = await consume(db, trace, four_domain_user)
    # The existing no-tools contract rejects the proposal in this response;
    # no further synthesis request is needed to prevent its dispatch.
    assert len(trace.calls) == 3
    assert all(not tools for _, tools in trace.calls[2:])
    assert not trace.dispatches
    assert trace.executor._read_repair_failures == 2
    assert done["turn_outcome"]["status"] != "complete"
