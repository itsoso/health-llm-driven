"""Screenshot regression: calendar-before-self is not a foreign owner."""

from datetime import datetime

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import (
    AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot,
)


REQUEST = "分析上周我的睡眠情况"
WINDOW = {"dimension": "sleep", "start_date": "2026-10-19",
          "end_date": "2026-10-25", "timezone": "Asia/Shanghai"}


def snapshot(text=REQUEST, *, owner=41, envelope_owner=41):
    envelope = AgentEnvelope(user_id=envelope_owner, channel="typed", text=text)
    context = ExecutionContext(
        user_id=owner, channel="typed", timezone="Asia/Shanghai",
        current_time=datetime.fromisoformat("2026-10-26T11:35:00+08:00"),
    )
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


@pytest.mark.parametrize("text", [
    REQUEST, "查询上周我的睡眠",
    "分析上周本人的睡眠情况", "分析我的上周睡眠情况",
])
@pytest.mark.parametrize("tool", ["health_query", "health_query_batch"])
def test_self_sleep_analysis_binds_previous_calendar_week(text, tool):
    turn = snapshot(text)
    assert not health_read_has_nonself_subject(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert scope.query("sleep") == WINDOW
    query = {"dimension": "sleep", "days": 7}
    args = query if tool == "health_query" else {"queries": [query]}
    decision = decide_tool_capability(turn, ToolExecutionRequest(tool, args))
    assert decision.action == "allow", decision.reason
    assert decision.normalized_args == (WINDOW if tool == "health_query"
                                        else {"queries": [WINDOW]})


@pytest.mark.parametrize("text", [
    "分析上周张三的睡眠情况", "分析上周我妈妈的睡眠情况",
    "分析上周我朋友的睡眠情况", "分析上周张三和我的睡眠情况",
    "分析上周我和张三的睡眠情况", "分析过去张三和我的睡眠情况",
    "分析最近张三和我的睡眠情况", "分析上周我的睡眠和张三的睡眠",
    "不要分析上周我的睡眠情况", "如果需要，分析上周我的睡眠情况",
    "解释例句：‘分析上周我的睡眠情况’",
    "查询2026-02-30我的睡眠", "分析上周我的睡眠，只看午睡前",
])
def test_owner_order_does_not_authorize_foreign_or_inactive_reads(text):
    for tool, args in (
        ("health_query", {"dimension": "sleep"}),
        ("health_query_batch", {"queries": [{"dimension": "sleep"}]}),
    ):
        assert decide_tool_capability(snapshot(text), ToolExecutionRequest(tool, args)).action == "block"


@pytest.mark.parametrize("change", [
    {"user_id": 42}, {"owner_id": 42}, {"tenant_id": 42},
    {"start_date": "2026-10-01"}, {"end_date": "2026-10-26"},
    {"timezone": "UTC"}, {"dimension": "diet"},
])
def test_model_cannot_change_sleep_owner_window_or_dimension(change):
    for tool, args in (
        ("health_query", {**WINDOW, **change}),
        ("health_query_batch", {"queries": [{**WINDOW, **change}]}),
    ):
        assert decide_tool_capability(snapshot(), ToolExecutionRequest(tool, args)).action == "block"


def test_self_language_does_not_override_authenticated_identity():
    decision = decide_tool_capability(
        snapshot(envelope_owner=42), ToolExecutionRequest("health_query", {"dimension": "sleep"}),
    )
    assert decision.action == "block"


def test_analysis_does_not_authorize_writing_sleep():
    decision = decide_tool_capability(snapshot(), ToolExecutionRequest(
        "health_record", {"record_type": "sleep", "data": {"duration": 8}},
    ))
    assert decision.action == "block"


@pytest.mark.parametrize("date_text,target", [
    ("昨天", "2026-10-25"), ("上周一", "2026-10-19"),
    ("2026-10-20", "2026-10-20"),
])
def test_calendar_before_self_keeps_exact_day(date_text, target):
    decision = decide_tool_capability(snapshot(f"查询{date_text}我的睡眠"),
                                     ToolExecutionRequest("health_query", {"dimension": "sleep"}))
    assert decision.action == "allow", decision.reason
    assert decision.normalized_args == {**WINDOW, "start_date": target, "end_date": target}


@pytest.mark.asyncio
async def test_screenshot_real_gateway_and_reader_keep_owner_and_calendar(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch,
):
    """Actual Pi/gateway/DB reader; only model output and clock are synthetic."""
    import json
    from datetime import date

    from app.models.agent_conversation import AgentMessage
    from app.models.daily_health import GarminData
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor
    from app.twin.schema import HealthTwin, TwinMeta

    user, _ = auth_user_and_headers
    other = User(name="Synthetic other", email="sleep-owner-other@example.test")
    db.add(other)
    db.flush()
    now = datetime.fromisoformat("2026-10-26T11:35:00+08:00")
    original_clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, "now", classmethod(
        lambda cls, **kwargs: original_clock(cls, **{**kwargs, "now_utc": now})
    ))
    monkeypatch.setattr("app.utils.timezone.get_china_today", lambda: now.date())
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, uid, **kwargs:
                        HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))
    for uid, day, score in (
        (user.id, date(2026, 10, 19), 71), (user.id, date(2026, 10, 25), 79),
        (other.id, date(2026, 10, 21), 99),
        (user.id, date(2026, 10, 18), 98), (user.id, date(2026, 10, 26), 97),
    ):
        db.add(GarminData(user_id=uid, record_date=day, sleep_score=score,
                          total_sleep_duration=420))
    db.commit()

    def fingerprint():
        return [tuple(getattr(row, col.name) for col in GarminData.__table__.columns)
                for row in db.query(GarminData).order_by(GarminData.id).all()]

    before = fingerprint()
    executor = AgentExecutor(db)
    original_dispatch = executor._dispatch_tool_request
    calls, results = [], []

    async def provider(messages, tools):
        if not calls:
            yield {"type": "tool_calls", "tool_calls": [
                {"id": "sleep-last-week", "type": "function", "function": {
                    "name": "health_query", "arguments": json.dumps({"dimension": "sleep", "days": 7}),
                }},
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "上周（10月19日至25日）有两天睡眠记录，其余日期没有记录，不能判断整周睡眠状况。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def observe_dispatch(request, token):
        calls.append(request)
        result = await original_dispatch(request, token)
        results.append(json.loads(result))
        return result

    async def read_with_fixture_session(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)

    monkeypatch.setattr(executor, "_read_in_process", read_with_fixture_session)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "按工具证据回答。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", observe_dispatch)
    events = [event async for event in executor.run_stream(
        user.id, REQUEST, client_turn_id="sleep-calendar-owner-order",
    )]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    assert done["perf"]["agent_kernel"] == "pi"
    assert len(calls) == 1
    assert calls[0].arguments == WINDOW
    assert [(row["record_date"], row["sleep_score"]) for row in results[0]["records"]] == [
        ("2026-10-19", 71), ("2026-10-25", 79),
    ]
    assert "这次查询未执行" not in saved.content
    assert not done.get("write_receipts")
    assert fingerprint() == before
