"""Real oral tasks must compose without gaining another user's authority."""

from datetime import datetime
import pytest
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    TurnSnapshot,
    ToolExecutionRequest,
)


def decide(message, tool, args):
    env = AgentEnvelope(user_id=41, channel="typed", text=message)
    ctx = ExecutionContext(
        current_time=datetime.fromisoformat("2026-09-13T09:00:00+08:00"),
        timezone="Asia/Shanghai",
        user_id=41,
        channel="typed",
    )
    snapshot = TurnSnapshot(env, ctx, build_intent_frame(env, ctx))
    return decide_tool_capability(snapshot, ToolExecutionRequest(tool, args))


@pytest.mark.parametrize(
    "message",
    [
        "获取佳明的数据，同步一下，主动触发一下同步。",
        "麻烦把我的佳明数据刷新一下，然后看看昨晚睡得怎么样。",
        "同步一下佳明，再分析昨晚睡眠。",
    ],
)
def test_explicit_owned_sync_is_not_a_whole_sentence_password(message):
    d = decide(message, "health_record", {"record_type": "garmin_sync", "data": {}})
    assert d.action == "allow", d.reason


@pytest.mark.parametrize(
    "message",
    [
        "昨天晚上我睡得怎么样？佳明的数据同步完了吗？",
        "帮我看一下昨晚的睡眠，再说说数据有没有同步。",
        "同步一下佳明，再分析昨晚睡眠。",
    ],
)
def test_composed_read_keeps_frozen_wake_date(message):
    d = decide(message, "health_query", {"dimension": "sleep", "days": 30})
    assert d.action == "allow", d.reason
    assert d.normalized_args == {
        "dimension": "sleep",
        "start_date": "2026-09-13",
        "end_date": "2026-09-13",
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.parametrize("dimension", ["diet", "sleep"])
def test_retrospective_task_can_read_multiple_declared_domains(dimension):
    d = decide("分析我昨天的行动。", "health_query", {"dimension": dimension})
    assert d.action == "allow", d.reason
    assert d.normalized_args["start_date"] == "2026-09-12"


@pytest.mark.parametrize(
    "message",
    [
        "佳明的数据同步完了吗？",
        "不要同步佳明，查昨晚睡眠。",
        "同步我朋友的佳明数据。",
        "假如我说同步佳明的数据。",
        "分析以下例句：同步佳明的数据。",
    ],
)
def test_status_question_or_unowned_and_quoted_text_does_not_start_sync(message):
    assert (
        decide(
            message, "health_record", {"record_type": "garmin_sync", "data": {}}
        ).action
        == "block"
    )


@pytest.mark.parametrize(
    "message",
    [
        "分析我朋友昨天的行动。",
        "假如分析我昨天的行动。",
        "不要分析我昨天的行动。",
        "分析以下例句：分析我昨天的行动。",
        "今天睡眠怎么样，删除昨天的饮食。",
    ],
)
def test_composition_cannot_inherit_quoted_nonself_or_mutating_authority(message):
    assert decide(message, "health_query", {"dimension": "sleep"}).action == "block"


def test_composed_read_does_not_authorize_unrequested_domain_or_model_date():
    q = "昨天晚上我睡得怎么样？佳明的数据同步完了吗？"
    assert decide(q, "health_query", {"dimension": "genetic"}).action == "block"
    assert (
        decide(
            q,
            "health_query",
            {
                "dimension": "sleep",
                "start_date": "2020-01-01",
                "end_date": "2020-01-01",
            },
        ).action
        == "block"
    )


@pytest.mark.asyncio
async def test_pi_can_repair_read_parameters_without_losing_tools(
    db, auth_user_and_headers, monkeypatch
):
    import json
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    dispatched = []

    async def provider(messages, tools):
        calls.append(tools)
        if len(calls) <= 2:
            if len(calls) == 2:
                assert tools, (
                    "repairable read rejection must not force text-only synthesis"
                )
            dimension = "diet" if len(calls) == 1 else "sleep"
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": f"read-{len(calls)}",
                        "type": "function",
                        "function": {
                            "name": "health_query",
                            "arguments": json.dumps({"dimension": dimension}),
                        },
                    }
                ],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "已核对昨晚的睡眠记录，记录完整。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def dispatch(request, token):
        dispatched.append(request)
        return json.dumps(
            {
                "dimension": "sleep",
                "window": {
                    k: v for k, v in request.arguments.items() if k != "dimension"
                },
                "sync_check": {"lookup_status": "available", "bound": False},
                "availability": "partial",
                "records": [
                    {
                        "record_date": executor._agent_kernel_reference_now()
                        .date()
                        .isoformat(),
                        "sleep_score": 80,
                    }
                ],
            }
        )

    monkeypatch.setattr(
        executor, "_build_system_prompt", lambda *a, **k: "Use tools for records."
    )
    monkeypatch.setattr(
        executor, "_build_system_knowledge_prompt_context", lambda *a, **k: ""
    )
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    events = [
        e
        async for e in executor.run_stream(
            user.id,
            "昨晚我睡得怎么样？佳明的数据同步完了吗？",
            client_turn_id="scope-repair",
        )
    ]
    assert len(dispatched) == 1
    assert dispatched[0].arguments["dimension"] == "sleep"
    assert len(calls) == 3
    assert events[-1]["data"]["perf"]["agent_kernel"] == "pi"
    assert events[-1]["data"]["turn_outcome"]["status"] == "complete"
