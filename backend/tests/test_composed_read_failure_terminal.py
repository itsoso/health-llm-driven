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
