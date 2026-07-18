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
