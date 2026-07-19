import pytest

from app.services.agent_executor import AgentExecutor


@pytest.mark.asyncio
async def test_read_tool_retry_hides_transient_first_failure(db):
    executor = AgentExecutor(db)
    attempts = 0

    async def fake_execute_tool(tool_name, args_raw, user_token):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return "Error: 健康数据查询执行失败，请稍后重试。"
        return '{"success":true,"data":[]}'

    executor._execute_tool = fake_execute_tool
    events = [
        item
        async for item in executor._run_tool_with_progress(
            "health_query", "{}", None, "正在查询健康数据"
        )
    ]

    assert attempts == 2
    assert events[-1] == ("result", '{"success":true,"data":[]}')
    assert any(
        kind == "heartbeat" and payload["data"]["detail"] == "retrying"
        for kind, payload in events
    )
    assert executor._agent_kernel_tool_retry_count == 1


@pytest.mark.asyncio
async def test_write_tool_failure_is_returned_without_retry(db):
    executor = AgentExecutor(db)
    attempts = 0

    async def fake_execute_tool(tool_name, args_raw, user_token):
        nonlocal attempts
        attempts += 1
        return "Error: 写入服务暂时不可用，请稍后重试。"

    executor._execute_tool = fake_execute_tool
    events = [
        item
        async for item in executor._run_tool_with_progress(
            "health_record", "{}", None, "正在记录健康数据"
        )
    ]

    assert attempts == 1
    assert events == [("result", "Error: 写入服务暂时不可用，请稍后重试。")]
    assert executor._agent_kernel_tool_retry_count == 0


@pytest.mark.asyncio
async def test_model_scope_refusal_recovery_reasks_without_relaxing_safety_boundary(db):
    executor = AgentExecutor(db)
    captured_messages = []

    async def fake_fallback(messages):
        captured_messages.extend(messages)
        return {
            "content": "可以基于最近 7 天的记录分析睡眠趋势，并给出下一步建议。",
            "finish_reason": "stop",
        }

    executor._call_llm_fallback_provider = fake_fallback

    recovered = await executor._recover_model_scope_refusal(
        [{"role": "user", "content": "帮我分析最近睡眠"}]
    )

    assert recovered == "可以基于最近 7 天的记录分析睡眠趋势，并给出下一步建议。"
    recovery_prompt = captured_messages[-1]["content"]
    assert "不要给出诊断、处方或停药指令" in recovery_prompt


@pytest.mark.asyncio
async def test_model_scope_refusal_recovery_discards_another_refusal(db):
    executor = AgentExecutor(db)

    async def fake_fallback(_messages):
        return {"content": "抱歉，我无法提供诊断或处方建议。", "finish_reason": "stop"}

    executor._call_llm_fallback_provider = fake_fallback

    recovered = await executor._recover_model_scope_refusal(
        [{"role": "user", "content": "帮我分析最近睡眠"}]
    )

    assert recovered == ""


@pytest.mark.asyncio
async def test_model_scope_refusal_is_buffered_until_recovery_answer(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    fallback_calls = 0

    async def refusal_stream(_messages, _tools):
        yield {"type": "content", "text": "抱歉，"}
        yield {"type": "content", "text": "我只能记录数据，无法提供分析和建议。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def recovered_fallback(_messages):
        nonlocal fallback_calls
        fallback_calls += 1
        return {"content": "可以基于已有记录分析，并给出下一步建议。", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    monkeypatch.setattr(executor, "_call_llm_stream", refusal_stream)
    monkeypatch.setattr(executor, "_call_llm_fallback_provider", recovered_fallback)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="分析我的睡眠情况",
            user_auth_token="test-token",
            client_turn_id="turn-model-scope-recovery",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert fallback_calls == 1
    assert "抱歉" not in rendered
    assert rendered == "可以基于已有记录分析，并给出下一步建议。"
