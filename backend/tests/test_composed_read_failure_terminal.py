"""A transient full-scope read failure has a bounded, truthful terminal path."""
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_agent_read_repair_round_budget import (
    QUERY, GOOD, ANSWER, batch_trace, consume,
    four_domain_user as four_domain_user, owned_data as owned_data, clock as clock,
    _isolate_twin_cache as _isolate_twin_cache,
)

ERROR = "Error: 查询失败，请稍后重试。"


@pytest.mark.parametrize("boundary", [
    "full", "partial", "date", "owner", "mismatched_tool", "latest_denial", "daily", "unscoped",
    "sync", "pending", "write", "exercise", "clinician",
])
def test_parameter_repair_does_not_require_verified_data_or_reset_budget(
    db, four_domain_user, monkeypatch, boundary,
):
    from app.services.agent_kernel.types import ToolExecutionResult

    executor, decision = setup_executor(db, four_domain_user)
    queries = [dict(query) for query in decision.normalized_args["queries"]]
    if boundary == "partial": queries.pop()
    elif boundary == "date": queries[-1]["start_date"] = "2026-09-01"
    elif boundary == "owner": queries[-1]["user_id"] = four_domain_user.id + 1
    decision = replace(decision, normalized_args={"queries": queries})
    executor._turn_composed_read_executions = [ToolExecutionResult(
        tool_name="health_query" if boundary == "mismatched_tool" else "health_query_batch",
        content=ERROR, decision=decision,
    )]
    if boundary == "latest_denial":
        executor._turn_composed_read_executions.append(ToolExecutionResult(
            tool_name="health_query_batch", content=ERROR, decision=replace(decision, action="block")))
    elif boundary == "daily": executor._turn_daily_read_plan = object()
    elif boundary == "unscoped": executor._agent_kernel_snapshot = None
    elif boundary == "sync": executor._turn_sync_attempted = True
    elif boundary == "pending": executor._agent_kernel_pending_confirmation_tools = ["synthetic"]
    elif boundary == "write":
        snapshot = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(snapshot, intent=replace(snapshot.intent, is_write=True))
    elif boundary == "exercise":
        monkeypatch.setattr("app.services.agent_kernel.exercise_plan_scope.resolve_exercise_plan_scope", lambda text: object())
    elif boundary == "clinician":
        from types import SimpleNamespace
        monkeypatch.setattr("app.services.agent_executor.classify_clinician_turn", lambda text: SimpleNamespace(kind="feedback"))
    executor._read_repair_failures = 1
    assert executor._scoped_read_parameters_repaired() == (boundary == "full")
    assert executor._read_repair_failures == 1
    assert not executor._force_no_tools_synthesis
    executor._consume_read_repair_failure()
    assert executor._read_repair_failures == 2
    assert executor._force_no_tools_synthesis


def setup_executor(db, user):
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = QUERY
    executor._start_agent_kernel_turn(user_id=user.id, message=QUERY, channel="typed")
    scope = resolve_owned_read_scope(executor._agent_kernel_snapshot)
    decision = decide_tool_capability(executor._agent_kernel_snapshot,
        ToolExecutionRequest("health_query_batch", {"queries": list(scope.queries)}))
    assert decision.action == "allow"
    executor._agent_kernel_last_decision = decision
    return executor, decision


@pytest.mark.parametrize("boundary", [
    "none", "no_retry", "success", "parameter", "blocked", "partial", "duplicate", "different_date",
    "sync", "pending", "already_verified", "daily", "write",
])
def test_terminal_requires_exact_pure_scope_and_exhausted_transient_retry(db, four_domain_user, monkeypatch, boundary):
    executor, decision = setup_executor(db, four_domain_user)
    result, attempt = ERROR, 1
    if boundary == "no_retry": attempt = 0
    elif boundary == "success": result = '{"status":"success","records":[]}'
    elif boundary == "parameter": result = "Error: 日历批查询参数无效"
    elif boundary == "blocked": executor._agent_kernel_last_decision = replace(decision, action="block")
    elif boundary in {"partial", "duplicate", "different_date"}:
        queries = [dict(q) for q in decision.normalized_args["queries"]]
        if boundary == "partial": queries.pop()
        elif boundary == "duplicate": queries.append(dict(queries[0]))
        else: queries[0]["start_date"] = "2026-09-01"
        executor._agent_kernel_last_decision = replace(decision, normalized_args={"queries": queries})
    elif boundary == "sync":
        monkeypatch.setattr("app.services.agent_kernel.read_task_scope.has_owned_sync_instruction", lambda text: True)
    elif boundary == "pending": executor._agent_kernel_pending_confirmation_tools = ["synthetic"]
    elif boundary == "already_verified": monkeypatch.setattr(executor, "_all_scoped_reads_verified", lambda: True)
    elif boundary == "daily": executor._turn_daily_read_plan = object()
    elif boundary == "write":
        snapshot = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(snapshot, intent=replace(snapshot.intent, is_write=True))
    executor._stop_exhausted_composed_read_retry("health_query_batch", result, attempt)
    assert executor._turn_composed_read_retry_exhausted == (boundary == "none")
    assert executor._read_repair_failures == 0
    executor._reset_read_repair_budget()
    assert not executor._turn_composed_read_retry_exhausted


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
async def test_retry_exhaustion_stops_siblings_and_next_turn_recovers(db, four_domain_user, monkeypatch, panel):
    trace = batch_trace(db, monkeypatch, [[*GOOD,
        ("knowledge_search", {"query": "睡眠健康"}),
        ("health_query", {"dimension": "sleep", "days": 7})], ANSWER])
    from app.services import agent_longitudinal_read as reads
    original = reads.read_longitudinal_health_query
    def failed(*args, **kwargs): raise RuntimeError("synthetic_read_unavailable")
    monkeypatch.setattr(reads, "read_longitudinal_health_query", failed)
    done, saved = await consume(db, trace, four_domain_user, panel=panel)
    assert len(trace.calls) == 1
    assert len(trace.dispatches) == 2
    assert all(r.tool_name == "health_query_batch" for r in trace.dispatches)
    assert done["turn_outcome"]["status"] == "failed"
    assert "未完成" in saved.content
    assert trace.executor._turn_composed_read_retry_exhausted
    monkeypatch.setattr(reads, "read_longitudinal_health_query", original)
    trace.steps[1:] = [GOOD, ANSWER]
    done, _ = await consume(db, trace, four_domain_user, panel=panel)
    assert done["turn_outcome"]["status"] == "complete"
    assert not trace.executor._turn_composed_read_retry_exhausted


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("partial", [False, True])
async def test_transient_recovery_and_partial_batch_keep_useful_work(db, four_domain_user, monkeypatch, panel, partial):
    first = [("health_query_batch", {"queries": [{"dimension": "diet", "days": 7}]})] if partial else GOOD
    trace = batch_trace(db, monkeypatch, [first, GOOD, ANSWER] if partial else [GOOD, ANSWER])
    from app.services import agent_longitudinal_read as reads
    original = reads.read_longitudinal_health_query
    attempts = 0
    def transient(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts <= (2 if partial else 1): raise RuntimeError("synthetic_read_unavailable")
        return original(*args, **kwargs)
    monkeypatch.setattr(reads, "read_longitudinal_health_query", transient)
    done, _ = await consume(db, trace, four_domain_user, panel=panel)
    assert done["turn_outcome"]["status"] == "complete"
    assert not trace.executor._turn_composed_read_retry_exhausted
    assert len(trace.dispatches) == (3 if partial else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
async def test_terminal_retains_prior_verified_dimension(db, four_domain_user, monkeypatch, panel):
    trace = batch_trace(db, monkeypatch, [[("health_query", {"dimension": "diet", "days": 7})], GOOD, ANSWER])
    from app.services import agent_longitudinal_read as reads
    original = reads.read_longitudinal_health_query
    attempts = 0
    def transient(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts > 1: raise RuntimeError("synthetic_read_unavailable")
        return original(*args, **kwargs)
    monkeypatch.setattr(reads, "read_longitudinal_health_query", transient)
    done, saved = await consume(db, trace, four_domain_user, panel=panel)
    assert done["turn_outcome"]["status"] == "partial"
    assert any(g["goal_id"] == "diet" and g["status"] == "verified" for g in done["turn_outcome"]["goals"])
    assert "200千卡" in saved.content
    assert trace.executor._turn_composed_read_retry_exhausted


@pytest.mark.parametrize("continuation", [False, True])
def test_sync_status_goal_excludes_full_scope_early_terminal(db, four_domain_user, continuation):
    from app.services.agent_kernel.types import ActionableReference
    from app.services.agent_kernel.read_task_scope import resolve_sync_status_query
    from app.services.agent_read_task_continuation import read_task_metadata
    query = "查看我昨天的睡眠和饮食，佳明数据同步完成了吗？"
    executor = AgentExecutor(db)
    executor._current_user_id = four_domain_user.id
    executor._current_turn_user_message = query
    executor._start_agent_kernel_turn(user_id=four_domain_user.id, message=query, channel="typed")
    state = executor._agent_kernel_snapshot
    scope = resolve_owned_read_scope(state)
    if continuation:
        prior = read_task_metadata(state, scope, sync_status=True)
        assert prior is not None
        executor._start_agent_kernel_turn(user_id=four_domain_user.id, message="再查一下", channel="typed")
        state = replace(executor._agent_kernel_snapshot, actionable_references=(
            ActionableReference(kind="owned_read_task", source_message_id="1", data=prior),))
        executor._agent_kernel_snapshot = state
        scope = resolve_owned_read_scope(state)
    assert resolve_sync_status_query(state) is not None
    decision = decide_tool_capability(state, ToolExecutionRequest("health_query_batch", {"queries": list(scope.queries)}))
    assert decision.action == "allow"
    executor._agent_kernel_last_decision = decision
    executor._stop_exhausted_composed_read_retry("health_query_batch", ERROR, 1)
    assert not executor._turn_composed_read_retry_exhausted
    from app.services.agent_kernel.types import ToolExecutionResult
    executor._turn_composed_read_executions = [ToolExecutionResult(
        tool_name="health_query_batch", content=ERROR, decision=decision)]
    assert not executor._scoped_read_parameters_repaired()


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
async def test_failed_batch_does_not_skip_sibling_sync_status(db, four_domain_user, monkeypatch, panel):
    query = "查看我昨天的睡眠和饮食，佳明数据同步完成了吗？"
    trace = batch_trace(db, monkeypatch, [[
        ("health_query_batch", {"queries": [{"dimension": d, "start_date": "2026-09-12",
           "end_date": "2026-09-12", "timezone": "Asia/Shanghai"} for d in ("sleep", "diet")]}),
        ("health_query", {"dimension": "garmin"})], ANSWER])
    from app.services import agent_query_window as reads
    def failed(*args, **kwargs): raise RuntimeError("synthetic_read_unavailable")
    monkeypatch.setattr(reads, "read_calendar_health_query", failed)
    done, _ = await consume(db, trace, four_domain_user, panel=panel, query=query)
    assert any(r.tool_name == "health_query" and r.arguments.get("dimension") == "garmin" for r in trace.dispatches)
    assert not trace.executor._turn_composed_read_retry_exhausted
    assert done["turn_outcome"]["status"] != "complete"
