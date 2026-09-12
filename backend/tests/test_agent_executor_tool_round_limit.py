import pytest

from app.services.agent_executor import AgentExecutor, MAX_TOOL_ROUNDS, INTERRUPTED_COMPLETION_NOTICE


def _stream_from(fake_call_llm):
    """适配旧式 fake_call_llm 到 run_stream 现用的 _call_llm_stream 事件流 seam。"""
    async def fake_call_llm_stream(messages, tools):
        result = await fake_call_llm(messages, tools)
        if isinstance(result, dict):
            content = result.get("content") or ""
            if content:
                yield {"type": "content", "text": content}
            tool_calls = result.get("tool_calls")
            if tool_calls:
                yield {"type": "tool_calls", "tool_calls": tool_calls}
            yield {"type": "finish", "finish_reason": result.get("finish_reason")}
        else:
            text = str(result or "")
            if text:
                yield {"type": "content", "text": text}
            yield {"type": "finish", "finish_reason": "stop"}

    return fake_call_llm_stream


@pytest.mark.asyncio
async def test_pi_tool_round_limit_interrupts_without_extra_model_call(
    db, auth_user_and_headers
):
    """Pi stops at its configured turn budget and reports an honest interruption."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        last_content = str(messages[-1].get("content") or "")
        if "工具查询轮次已经用完" in last_content:
            return "最终分析：已基于前面查到的数据完成代谢健康复盘。"
        return {
            "content": "继续查询数据。\n",
            "tool_calls": [
                {
                    "id": f"call_{len(calls)}",
                    "type": "function",
                    "function": {
                        "name": "health_query",
                        "arguments": '{"dimension":"weight","days":7}',
                    },
                }
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        return '{"records":[{"date":"2026-05-18","weight":71.2}]}'

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="分析我最近的代谢健康",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert INTERRUPTED_COMPLETION_NOTICE in rendered
    assert "最终分析" not in rendered
    assert "继续查询数据" not in rendered
    assert len(calls) == MAX_TOOL_ROUNDS
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["llm_rounds"] == MAX_TOOL_ROUNDS
    assert events[-1]["data"]["completion_status"] == "interrupted"
    assert events[-1]["data"]["write_receipts"] == []


@pytest.mark.asyncio
async def test_pi_retains_declared_tools_until_model_finishes_after_tool_result(
    db, auth_user_and_headers
):
    """The model sees its real tool result and finishes while tools stay declared."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) == 2:
            assert any(item.get("role") == "tool" for item in messages)
            return "最终分析：已基于前面查到的数据完成代谢健康复盘。"
        return {
            "content": "继续查询数据。\n",
            "tool_calls": [
                {
                    "id": f"call_{len(calls)}",
                    "type": "function",
                    "function": {
                        "name": "health_query",
                        "arguments": '{"dimension":"weight","days":7}',
                    },
                }
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        return '{"records":[{"date":"2026-05-18","weight":71.2}]}'

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="分析我最近的代谢健康",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert "最终分析" in rendered
    assert len(calls) == 2
    assert calls[0]["tool_count"] > 0
    assert calls[1]["tool_count"] == calls[0]["tool_count"]
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["llm_rounds"] == 2
