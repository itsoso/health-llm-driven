"""Exact screenshot request: owned candidate read, never an invented event."""
from datetime import datetime

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability, SPECIALIST_READ_ONLY_TOOLS
from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot


def snapshot(text):
    envelope = AgentEnvelope(user_id=41, channel="typed", text=text)
    context = ExecutionContext(user_id=41, channel="typed", timezone="Asia/Shanghai",
                               current_time=datetime.fromisoformat("2026-10-09T17:00:00+00:00"))
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


@pytest.mark.parametrize("text", [
    "分析刚才的运动", "分析我刚才的运动", "请帮我分析一下刚刚的运动记录。",
    "看看我刚才的锻炼数据", "复盘刚刚的训练",
])
def test_recent_workout_reads_current_local_day_candidates(text):
    turn = snapshot(text)
    assert not health_read_has_nonself_subject(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    expected = {"dimension": "workout", "start_date": "2026-10-10",
                "end_date": "2026-10-10", "timezone": "Asia/Shanghai"}
    assert scope.query("workout") == expected
    assert "recent_workout_candidates_not_identified_event" in scope.limitations
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query", {"dimension": "workout"}))
    assert decision.action == "allow", decision.reason
    assert decision.normalized_args == expected


@pytest.mark.parametrize("text", [
    "分析小王刚才的运动", "分析我朋友刚才的运动", "分析刚才Alice的运动",
    "不要分析刚才的运动", "解释例句：‘分析刚才的运动’", "如果有空，分析刚才的运动",
    "分析刚才的运动，只看别人的记录", "分析刚才的运动，范围是去年",
    "刚才的运动", "刚才的运动不错", "刚才的运动是谁的",
])
def test_other_owner_and_unconsumed_restrictions_stay_blocked(text):
    decision = decide_tool_capability(snapshot(text), ToolExecutionRequest("health_query", {"dimension": "workout"}))
    assert decision.action == "block"


@pytest.mark.parametrize("extra", [
    {"user_id": 42}, {"owner_id": 42}, {"tenant_id": 42},
    {"start_date": "2026-10-01"}, {"end_date": "2026-10-11"}, {"timezone": "UTC"},
    {"dimension": "sleep"},
])
def test_model_cannot_widen_recent_workout_scope(extra):
    decision = decide_tool_capability(snapshot("分析刚才的运动"), ToolExecutionRequest(
        "health_query", {"dimension": "workout", **extra}))
    assert decision.action == "block"


def test_recent_workout_read_does_not_authorize_sync_or_writes():
    for args in ({"record_type": "garmin_sync", "data": {}},
                 {"record_type": "exercise", "data": {"duration_minutes": 30}}):
        assert decide_tool_capability(snapshot("分析刚才的运动"),
            ToolExecutionRequest("health_record", args)).action == "block"


@pytest.mark.parametrize("owner,envelope_owner", [(42, 41), (0, 0), (1, True), (True, 1)])
@pytest.mark.parametrize("tool,args", [
    ("health_query", {"dimension": "workout"}),
    ("health_query_batch", {"queries": [{"dimension": "workout"}]}),
])
def test_invalid_authenticated_owner_never_falls_back_to_rolling_read(owner, envelope_owner, tool, args):
    from dataclasses import replace
    turn = snapshot("分析刚才的运动")
    turn = replace(turn, context=replace(turn.context, user_id=owner),
                   envelope=replace(turn.envelope, user_id=envelope_owner))
    decision = decide_tool_capability(turn, ToolExecutionRequest(tool, args))
    assert decision.action == "block"


@pytest.mark.parametrize("tool,args", [
    ("health_analysis", {"analysis_type": "exercise", "days": 365}),
    ("health_manage", {"record_type": "exercise", "operation": "list"}),
] + [(tool, {}) for tool in sorted(SPECIALIST_READ_ONLY_TOOLS)])
def test_other_tools_cannot_bypass_candidate_window(tool, args):
    assert decide_tool_capability(snapshot("分析刚才的运动"), ToolExecutionRequest(tool, args)).action == "block"


def test_batch_uses_same_owned_candidate_window():
    turn = snapshot("分析刚才的运动")
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
        "queries": [{"dimension": "workout"}],
    }))
    assert decision.action == "allow"
    assert decision.normalized_args == {"queries": list(resolve_owned_read_scope(turn).queries)}
    assert decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
        "queries": [{"dimension": "workout", "owner_id": 42}],
    })).action == "block"


@pytest.mark.asyncio
@pytest.mark.parametrize("has_record", [True, False])
async def test_screenshot_request_reaches_real_owned_reader_and_saved_reply(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, has_record,
):
    import json
    from datetime import timedelta
    from app.models.agent_conversation import AgentMessage
    from app.models.daily_health import WorkoutRecord
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor
    from app.twin.schema import HealthTwin, TwinMeta

    user, _ = auth_user_and_headers
    other = User(name="Synthetic other", email="recent-workout-other@example.test")
    db.add(other)
    db.flush()
    now = datetime.fromisoformat("2026-10-10T09:00:00+08:00")
    original_clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, "now", classmethod(
        lambda cls, **kwargs: original_clock(cls, **{**kwargs, "now_utc": now})))
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, uid, **kwargs:
        HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))
    own = WorkoutRecord(user_id=user.id, workout_date=now.date(),
                        workout_type="running", duration_seconds=1800)
    if has_record:
        db.add(own)
    db.add_all([
        WorkoutRecord(user_id=other.id, workout_date=now.date(), workout_type="walking"),
        WorkoutRecord(user_id=user.id, workout_date=now.date()-timedelta(days=1), workout_type="cycling"),
    ])
    db.commit()
    before = [(r.id, r.user_id, r.workout_date) for r in db.query(WorkoutRecord).order_by(WorkoutRecord.id)]
    executor = AgentExecutor(db)
    dispatch = executor._dispatch_tool_request
    calls, results = [], []

    async def provider(messages, tools):
        calls.append(tools)
        if len(calls) == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "recent-workout-read", "type": "function", "function": {
                    "name": "health_query", "arguments": json.dumps({"dimension": "workout"}),
                }}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "已查询运动记录。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def observe(request, token):
        result = await dispatch(request, token)
        results.append((request, json.loads(result)))
        return result

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "按工具证据回答。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", observe)
    events = [event async for event in executor.run_stream(
        user.id, "分析刚才的运动", client_turn_id=f"recent-workout-{has_record}")]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    assert done["perf"]["agent_kernel"] == "pi"
    assert {t["function"]["name"] for t in calls[0]} <= {"health_query", "health_query_batch", "knowledge_search"}
    assert len(results) == 1
    request, payload = results[0]
    assert request.tool_name == "health_query"
    assert request.arguments["start_date"] == request.arguments["end_date"] == "2026-10-10"
    assert [r["id"] for r in payload["records"]] == ([own.id] if has_record else [])
    assert payload["availability"] == ("available" if has_record else "no_data")
    assert "只能查询当前登录用户" not in saved.content
    assert "候选记录" in saved.content and "尚不能确认" in saved.content
    assert not done.get("write_receipts")
    assert [(r.id, r.user_id, r.workout_date) for r in db.query(WorkoutRecord).order_by(WorkoutRecord.id)] == before
