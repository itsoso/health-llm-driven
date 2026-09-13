"""Real Pi SSE progress must reflect structured tool failure, not JSON spelling."""

import json

import pytest

from app.api.agent import _persist_done_thinking_steps, _thought_step_from_agent_event
from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor


@pytest.fixture(autouse=True)
def isolate(isolated_agent_protocol_transport):
    """Use the real Pi protocol while prohibiting external provider/cache traffic."""


async def run_tool_result(db, user, monkeypatch, *, result, blocked=False):
    executor = AgentExecutor(db)
    rounds, dispatched = [], []

    async def provider(messages, tools):
        rounds.append(messages)
        if len(rounds) == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": "progress-proof",
                        "type": "function",
                        "function": {
                            "name": "health_query",
                            "arguments": json.dumps(
                                {"dimension": "diet" if blocked else "sleep"}
                            ),
                        },
                    }
                ],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "本轮查询结果以实际记录和执行状态为准。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def dispatch(request, token):
        dispatched.append(request)
        assert not blocked, "Policy-blocked query must never reach the data dispatcher"
        if result == "valid-zero":
            return json.dumps(
                {
                    "status": "success",
                    "dimension": "sleep",
                    "window": {
                        k: request.arguments[k]
                        for k in ("start_date", "end_date", "timezone")
                    },
                    "records": [
                        {
                            "record_date": request.arguments["start_date"],
                            "sleep_score": 0,
                            "total_sleep_duration": 0,
                            "error": "row annotation is data, not execution failure",
                        }
                    ],
                    "availability": "available",
                    "error": False,
                }
            )
        return result

    monkeypatch.setattr(
        executor,
        "_build_system_prompt",
        lambda *a, **k: "Use tools for verified records.",
    )
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    events = [
        event
        async for event in executor.run_stream(
            user.id,
            "查询今天的睡眠记录",
            client_turn_id="structured-progress",
        )
    ]
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["perf"]["agent_kernel"] == "pi"
    tool_events = [
        e
        for e in events
        if e.get("event") == "tool_result" and e["data"].get("tool") == "health_query"
    ]
    assert tool_events, "Exercise the emitted SSE, not only a result parsing helper"
    message = (
        db.query(AgentMessage)
        .filter(AgentMessage.id == events[-1]["data"]["message_id"])
        .one()
    )
    return tool_events, dispatched, message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        json.dumps(
            {
                "status": "rejected",
                "error_code": "health_query_dimension_conflict",
                "dispatch_started": False,
            }
        ),
        json.dumps({"status": "error", "error": "synthetic failure"}),
        json.dumps({"success": False, "records": [{"sleep_score": 80}]}),
        json.dumps({"ok": False, "records": [{"sleep_score": 80}]}),
        json.dumps({"status": "needs_confirmation"}),
        json.dumps({"status": "confirmation_required"}),
        "Error: synthetic failure",
    ],
)
async def test_structured_failure_never_emits_or_persists_acquired_data(
    db, auth_user_and_headers, monkeypatch, result
):
    user, _ = auth_user_and_headers
    events, dispatched, message = await run_tool_result(
        db, user, monkeypatch, result=result
    )
    assert dispatched
    assert all(e["data"]["success"] is False for e in events)
    steps = [_thought_step_from_agent_event(e) for e in events]
    assert all(step == "健康数据暂时不可用" for step in steps)
    _persist_done_thinking_steps(db, message.id, steps)
    db.refresh(message)
    assert message.meta["thinking_steps"] == ["健康数据暂时不可用"]
    assert message.meta["thinking_steps_kind"] == "safe_progress_summary"
    assert "已取得" not in json.dumps(
        message.meta["thinking_steps"], ensure_ascii=False
    )


@pytest.mark.asyncio
async def test_actual_gateway_rejection_has_no_dispatch_and_no_acquired_progress(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    events, dispatched, message = await run_tool_result(
        db, user, monkeypatch, result=None, blocked=True
    )
    assert not dispatched
    assert all(e["data"]["success"] is False for e in events)
    assert all(
        json.loads(e["data"]["result"])["dispatch_started"] is False for e in events
    )
    steps = [_thought_step_from_agent_event(e) for e in events]
    _persist_done_thinking_steps(db, message.id, steps)
    db.refresh(message)
    assert message.meta["thinking_steps"] == ["健康数据暂时不可用"]


@pytest.mark.asyncio
async def test_valid_zero_readings_and_nested_error_text_still_report_acquired_data(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    events, dispatched, message = await run_tool_result(
        db, user, monkeypatch, result="valid-zero"
    )
    assert dispatched and all(e["data"]["success"] is True for e in events)
    steps = [_thought_step_from_agent_event(e) for e in events]
    assert steps == ["已取得健康数据"]
    _persist_done_thinking_steps(db, message.id, steps)
    db.refresh(message)
    assert message.meta["thinking_steps"] == ["已取得健康数据"]
