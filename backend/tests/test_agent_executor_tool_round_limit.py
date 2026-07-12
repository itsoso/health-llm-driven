import pytest

from app.services.agent_executor import AgentExecutor, MAX_TOOL_ROUNDS


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
async def test_agent_stream_synthesizes_final_answer_when_tool_round_limit_is_hit(
    db, auth_user_and_headers
):
    """贪婪模型(即使 A2 合成轮不带 tools schema 仍持续吐结构化工具调用,
    DeepSeek 类实测行为)→ 只能靠 MAX_TOOL_ROUNDS 兜底,耗尽后强制 no-tools
    合成出最终答案,绝不把半成品/报错文案丢给用户。

    fake 的"该出最终答案了"信号锚定轮次耗尽的强制合成提示语,而不是
    `not tools`:A2(243e8cc8d)后工具执行过的下一轮就已不带 tools,
    `not tools` 不再等价于"轮次耗尽"。
    """
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
    assert "最终分析" in rendered
    assert "已达到最大推理轮次" not in rendered
    assert calls[-1]["tool_count"] == 0
    assert len(calls) == MAX_TOOL_ROUNDS + 1
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["llm_rounds"] == MAX_TOOL_ROUNDS + 1


@pytest.mark.asyncio
async def test_agent_stream_synthesis_round_drops_tools_after_tool_execution(
    db, auth_user_and_headers
):
    """A2(243e8cc8d)契约:上一轮执行过工具 → 下一轮是合成轮,对所有模型
    置空 tools(省 18KB schema prefill)。守规矩的模型(拿不到 tools 就直接
    作答)在第 2 轮产出最终答案,总共恰好 2 次 LLM 调用。"""
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
    assert calls[1]["tool_count"] == 0
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["llm_rounds"] == 2
