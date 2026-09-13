import json
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_pi_conversation_feedback_receives_history_but_no_health_tools(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_executor import AgentExecutor
    from app.models.agent_conversation import AgentConversation, AgentMessage

    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id)
    db.add(conv)
    db.flush()
    db.add_all(
        [
            AgentMessage(conversation_id=conv.id, role="user", content="今天我吃了啥"),
            AgentMessage(
                conversation_id=conv.id,
                role="assistant",
                content="请明确查询哪类记录以及日期。",
            ),
        ]
    )
    db.commit()
    executor = AgentExecutor(db)
    called = []

    async def provider(messages, tools):
        called.append((messages, tools))
        yield {
            "type": "content",
            "text": "刚才你已经给出了日期和饮食范围，我却重复追问了这些信息。这次回答没有完成你的查询。",
        }
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(
        executor, "_build_system_prompt", lambda *a, **k: "Answer feedback."
    )
    monkeypatch.setattr(
        executor, "_build_system_knowledge_prompt_context", lambda *a, **k: ""
    )
    dispatch = AsyncMock(
        side_effect=AssertionError("feedback must not dispatch health tools")
    )
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    events = [
        e
        async for e in executor.run_stream(
            user.id, "怎么变弱智了？", conversation_id=conv.id
        )
    ]
    assert called
    assert not called[0][1]
    assert any("请明确查询" in str(m.get("content")) for m in called[0][0])
    assert events[-1]["data"]["perf"]["agent_kernel"] == "pi"
    assert "重复追问" in db.get(AgentMessage, events[-1]["data"]["message_id"]).content
    dispatch.assert_not_called()


def test_verified_receipt_summary_excludes_pending_and_failed_receipts():
    from app.services.agent_executor import _write_rejection_with_receipt_context

    assert (
        _write_rejection_with_receipt_context("尚未完成。", [{"verified": False}])
        == "尚未完成。"
    )
    result = _write_rejection_with_receipt_context(
        "尚未完成。",
        [
            {"verified": False},
            {
                "verified": True,
                "resource_type": "diet",
                "resource_id": "1",
                "operation_id": "1",
            },
            {
                "verified": True,
                "resource_type": "diet",
                "resource_id": "1",
                "operation_id": "1",
            },
        ],
    )
    assert "1 项" in result
    assert "3 项" not in result


@pytest.mark.parametrize(
    "args",
    [
        {"plan": []},
        {"plan": "invalid"},
        {"queries": None},
        {"queries": [{"dimension": "sleep"}], "user_id": 42},
    ],
)
def test_composed_query_malformed_or_owner_args_fail_closed(args):
    from tests.test_agent_composed_read_scope import decide

    decision = decide("昨晚睡眠怎么样，佳明同步完了吗？", "health_query_batch", args)
    assert decision.action == "block"


def test_status_query_cannot_supply_another_owner():
    from tests.test_agent_composed_read_scope import decide

    d = decide(
        "佳明同步完了吗？", "health_query", {"dimension": "garmin", "user_id": 42}
    )
    assert d.action == "block"


@pytest.mark.asyncio
async def test_read_repair_budget_stops_dispatch_and_resets_next_turn(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import CapabilityDecision

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._start_agent_kernel_turn(
        user_id=user.id, message="分析昨晚睡眠", channel="typed"
    )
    attempted = []

    async def reject(name, args, token, **kwargs):
        attempted.append(args)
        executor._agent_kernel_record_capability_decision(
            name,
            CapabilityDecision("block", "health_query_dimension_conflict", name, args),
        )
        return json.dumps(
            {"status": "rejected", "error_code": "health_query_dimension_conflict"}
        )

    monkeypatch.setattr(executor, "_execute_tool_impl", reject)
    for dimension in ("diet", "hrv"):
        await executor._execute_tool("health_query", {"dimension": dimension}, None)
    result = json.loads(
        await executor._execute_tool("health_query", {"dimension": "sleep"}, None)
    )
    assert len(attempted) == 2
    assert result["error_code"] == "read_repair_budget_exhausted"
    assert result["dispatch_started"] is False
    executor._start_agent_kernel_turn(
        user_id=user.id, message="分析今天睡眠", channel="typed"
    )
    await executor._execute_tool("health_query", {"dimension": "sleep"}, None)
    assert len(attempted) == 3
