"""A closed factual lookup still goes through Pi, owner scope and read verification."""

from dataclasses import replace

import pytest
from app.config import settings
from app.models.agent_conversation import AgentMessage
from app.models.daily_health import GarminData

from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,  # noqa: PLC0414 - pytest fixture re-export
)
from tests.test_agent_coherence_pi_trajectories import (
    clock as clock,  # noqa: PLC0414 - pytest fixture re-export
)
from tests.test_agent_coherence_pi_trajectories import (
    owned_data as owned_data,  # noqa: PLC0414 - pytest fixture re-export
)
from tests.test_agent_coherence_pi_trajectories import (
    script_executor,
)

QUERY = "查询今天的睡眠记录"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["available", "empty"])
async def test_closed_lookup_uses_verified_read_without_planner_or_synthesis(
    db,
    owned_data,
    clock,
    monkeypatch,
    state,
):
    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    if state == "empty":
        db.query(GarminData).filter(GarminData.user_id == owned_data.id).delete()
        db.commit()
    trace = script_executor(db, monkeypatch, [])
    events = [
        event
        async for event in trace.executor.run_stream(
            owned_data.id,
            QUERY,
            channel="typed",
            client_caps=["genui-sleep-summary-v1"],
        )
    ]
    done = events[-1]["data"]
    assert not trace.calls and not trace.unexpected
    assert len(trace.dispatches) == 1
    assert trace.dispatches[0].tool_name == "health_query"
    assert trace.dispatches[0].arguments["start_date"] == clock[0].date().isoformat()
    assert done["turn_outcome"]["status"] == "complete"
    assert not done["write_receipts"]
    assert done["perf"]["model_call_count"] == 0
    saved = db.get(AgentMessage, done["message_id"])
    assert saved.content == "".join(
        e["data"]["content"] for e in events if e.get("event") == "token"
    )
    assert "睡眠" in saved.content
    assert "599" not in saved.content and "111" not in saved.content
    if state == "available":
        assert "80" in saved.content and "7小时" in saved.content
    else:
        assert "80" not in saved.content and "420" not in saved.content
    assert "模型推断" not in saved.content


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "truncated", "wrong_date"])
async def test_unverified_result_cannot_finish_as_fast_lookup(
    db, owned_data, clock, monkeypatch, failure
):
    from app.services import agent_query_window

    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    read = agent_query_window.read_calendar_health_query

    def broken(*args, **kwargs):
        if failure == "exception":
            raise RuntimeError("synthetic_read_failure")
        result = read(*args, **kwargs)
        if failure == "truncated":
            result["truncated"] = True
        else:
            result["window"]["start_date"] = "2000-01-01"
        return result

    monkeypatch.setattr(agent_query_window, "read_calendar_health_query", broken)
    trace = script_executor(db, monkeypatch, ["本次读取未完成，不能确认记录。"])
    events = [
        event
        async for event in trace.executor.run_stream(
            owned_data.id, QUERY, channel="typed"
        )
    ]
    done = events[-1]["data"]
    assert not trace.unexpected
    assert done["turn_outcome"]["status"] != "complete"
    assert done["perf"]["simple_lookup_rendered"] is False
    assert not done["write_receipts"]


@pytest.mark.asyncio
async def test_existing_conversation_keeps_model_planner_and_history(
    db, owned_data, clock, monkeypatch
):
    from app.models.agent_conversation import AgentConversation

    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    conv = AgentConversation(user_id=owned_data.id)
    db.add(conv)
    db.flush()
    db.add(
        AgentMessage(
            conversation_id=conv.id,
            role="user",
            content="此前的睡眠记录有误，不要据此判断恢复。",
        )
    )
    db.add(AgentMessage(conversation_id=conv.id, role="assistant", content="已了解。"))
    db.commit()
    trace = script_executor(db, monkeypatch, [("health_query", {"dimension": "sleep"})])
    events = [
        event
        async for event in trace.executor.run_stream(
            owned_data.id,
            QUERY,
            channel="typed",
            conversation_id=conv.id,
        )
    ]
    assert not trace.unexpected and len(trace.calls) == 1
    assert any("记录有误" in str(m.get("content")) for m in trace.calls[0][0])
    assert not events[-1]["data"]["perf"]["owned_read_preplanned"]


@pytest.mark.asyncio
@pytest.mark.parametrize("floor", ["casual", "high_stakes"])
async def test_closed_lookup_skips_optional_router_only_without_quality_floor(
    db,
    owned_data,
    clock,
    monkeypatch,
    floor,
):
    from tests.test_decision_routing import fake_result, wire

    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(settings, "decision_mode", "on")
    monkeypatch.setattr(settings, "decision_provider", "laya")
    monkeypatch.setattr(settings, "decision_admin_control_enabled", False)
    seen = wire(monkeypatch, fake_result("casual"))
    monkeypatch.setattr(
        "app.services.llm.task_routing.classify_answer_task_tier", lambda *a, **k: floor
    )
    trace = script_executor(
        db,
        monkeypatch,
        [
            ("health_query", {"dimension": "sleep"}),
            "仅展示本次返回的记录。",
        ]
        if floor == "high_stakes"
        else [],
    )
    events = [
        event
        async for event in trace.executor.run_stream(
            owned_data.id, QUERY, channel="typed"
        )
    ]
    assert not trace.unexpected
    assert len(seen) == (1 if floor == "high_stakes" else 0)
    assert events[-1]["data"]["perf"]["simple_lookup_route_skipped"] == (
        floor != "high_stakes"
    )


@pytest.mark.parametrize(
    "message",
    [
        "分析今天的睡眠记录",
        "查询今天的睡眠记录，给我建议",
        "查询妈妈今天的睡眠记录",
        "不要查询今天的睡眠记录",
        "如果查询今天的睡眠记录",
        "例句：查询今天的睡眠记录",
        "查询今天的睡眠记录并记录一杯水",
        "查询今天的睡眠记录，只看深睡",
        "查询今天的睡眠记录，我呼吸困难",
        "查询今天的睡眠记录并同步佳明",
    ],
)
def test_lookup_does_not_erase_other_goals_or_qualifiers(
    db, owned_data, monkeypatch, message
):
    executor = script_executor(db, monkeypatch, []).executor
    executor._current_user_id = owned_data.id
    executor._current_turn_user_message = message
    executor._start_agent_kernel_turn(
        user_id=owned_data.id, message=message, channel="typed"
    )
    assert executor._simple_record_lookup_scope() is None


@pytest.mark.parametrize(
    "boundary",
    [
        "owner",
        "context_owner",
        "text",
        "attachment",
        "pending",
        "sync",
        "failure",
        "denied",
        "floor",
    ],
)
def test_lookup_shortcut_fails_closed(db, owned_data, monkeypatch, boundary):
    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    executor = script_executor(db, monkeypatch, []).executor
    executor._current_user_id = owned_data.id
    executor._current_turn_user_message = QUERY
    executor._start_agent_kernel_turn(
        user_id=owned_data.id, message=QUERY, channel="typed"
    )
    if boundary == "owner":
        executor._current_user_id += 1
    if boundary == "context_owner":
        s = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(
            s, context=replace(s.context, user_id=owned_data.id + 1)
        )
    if boundary == "text":
        executor._current_turn_user_message = "查询昨天的睡眠记录"
    if boundary == "attachment":
        executor._current_turn_has_attachment = True
    if boundary == "pending":
        executor._agent_kernel_pending_confirmation_tools = ["health_record"]
    if boundary == "sync":
        executor._turn_sync_attempted = True
    if boundary == "failure":
        executor._agent_kernel_tool_failure_tools = ["health_query"]
    if boundary == "denied":
        executor._agent_kernel_capability_block_reasons = ["denied"]
    if boundary == "floor":
        executor._staged_answer_task_tier = "high_stakes"
    assert executor._simple_record_lookup_scope() is None
