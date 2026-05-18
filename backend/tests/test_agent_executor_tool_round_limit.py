import pytest

from app.services.agent_executor import AgentExecutor, MAX_TOOL_ROUNDS


@pytest.mark.asyncio
async def test_agent_stream_synthesizes_final_answer_when_tool_round_limit_is_hit(
    db, auth_user_and_headers
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if not tools:
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
    assert "已达到最大推理轮次" not in rendered
    assert calls[-1]["tool_count"] == 0
    assert len(calls) == MAX_TOOL_ROUNDS + 1
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["llm_rounds"] == MAX_TOOL_ROUNDS + 1
