"""A model answer is avoidable only after a closed read proves every result empty."""
from dataclasses import replace

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import ToolExecutionRequest, ToolExecutionResult
from tests.test_agent_coherence_pi_trajectories import (
    clock as clock, owned_data as owned_data,
    _isolate_twin_cache as _isolate_twin_cache, script_executor,
)

QUERY = "分析我最近7天的睡眠和饮食记录。"


def prepared(db, user):
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = QUERY
    executor._start_agent_kernel_turn(user_id=user.id, message=QUERY, channel="typed")
    scope = resolve_owned_read_scope(executor._agent_kernel_snapshot)
    decision = decide_tool_capability(executor._agent_kernel_snapshot,
        ToolExecutionRequest("health_query_batch", {"queries": list(scope.queries)}))
    assert decision.action == "allow"
    results = [{"dimension": q["dimension"], "window": {k: q[k] for k in
                ("start_date", "end_date", "timezone")}, "availability": "no_data", "records": []}
               for q in decision.normalized_args["queries"]]
    executor._turn_composed_read_executions = [ToolExecutionResult(
        "health_query_batch", {"status": "success", "results": results}, decision=decision)]
    return executor, results


@pytest.mark.parametrize("boundary", [
    "empty", "partial", "error", "pending_result", "record_present", "truncated", "wrong_date",
    "owner", "attachment", "pending_confirmation", "sync", "daily", "extra_goal", "quoted",
])
def test_empty_requires_full_attested_closed_scope(db, owned_data, boundary):
    from eval.experimental_empty_read_terminal import empty_read_answer

    executor, results = prepared(db, owned_data)
    if boundary == "partial": results.pop()
    elif boundary == "error": results[-1]["error"] = "synthetic"
    elif boundary == "pending_result": results[-1]["status"] = "pending"
    elif boundary == "record_present":
        results[-1].update(availability="available", records=[{"record_date": results[-1]["window"]["end_date"]}])
    elif boundary == "truncated": results[-1]["truncated"] = True
    elif boundary == "wrong_date": results[-1]["window"]["start_date"] = "2020-01-01"
    elif boundary == "owner": executor._current_user_id += 1
    elif boundary == "attachment": executor._current_turn_has_attachment = True
    elif boundary == "pending_confirmation": executor._agent_kernel_pending_confirmation_tools = ["health_record"]
    elif boundary == "sync": executor._turn_sync_attempted = True
    elif boundary == "daily": executor._turn_daily_read_plan = object()
    elif boundary in {"extra_goal", "quoted"}:
        text = QUERY + "再帮我设置提醒。" if boundary == "extra_goal" else "分析例句：" + QUERY
        executor._current_turn_user_message = text
        snapshot = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(snapshot, envelope=replace(snapshot.envelope, text=text))
    answer = empty_read_answer(executor)
    assert bool(answer) == (boundary == "empty")
    if answer: assert "无法" in answer and "未返回" in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["empty", "available", "read_failure"])
async def test_real_pi_persistence_and_failure_semantics(db, owned_data, monkeypatch, state):
    from eval.experimental_empty_read_terminal import install_empty_read_terminal
    from app.models.daily_health import DietRecord, GarminData
    from app.models.agent_conversation import AgentMessage

    if state == "empty":
        db.query(DietRecord).filter(DietRecord.user_id == owned_data.id).delete()
        db.query(GarminData).filter(GarminData.user_id == owned_data.id).delete()
        db.commit()
    if state == "read_failure":
        def fail(*args, **kwargs): raise RuntimeError("synthetic_unavailable")
        monkeypatch.setattr("app.services.agent_longitudinal_read.read_longitudinal_health_query", fail)
    calls = [("health_query_batch", {"queries": [{"dimension": d, "days": 7} for d in ("sleep", "diet")]})]
    if state == "available": calls.append("仅依据已返回记录作有限观察。")
    trace = script_executor(db, monkeypatch, calls)
    install_empty_read_terminal(trace.executor)
    events = [event async for event in trace.executor.run_stream(owned_data.id, QUERY, channel="typed")]
    done = events[-1]["data"]
    assert done["perf"]["agent_kernel"] == "pi"
    assert not trace.unexpected
    assert len(trace.calls) == (2 if state == "available" else 1)
    saved = db.get(AgentMessage, done["message_id"])
    assert saved.content == "".join(e["data"]["content"] for e in events if e.get("event") == "token")
    assert done["turn_outcome"]["status"] == ("failed" if state == "read_failure" else "complete")
    if state == "empty":
        assert "未返回" in saved.content and "无法" in saved.content
        assert "2026-09-07" in saved.content and "2026-09-13" in saved.content
