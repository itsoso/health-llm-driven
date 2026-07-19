# -*- coding: utf-8 -*-
"""Provider/API 原始异常不得进入小巴可见回复或落库内容。"""

from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor
from app.services.llm.error_messages import safe_tool_error_message


RAW_TOKENPLAN_QUOTA_ERROR = (
    "Error code: 429 - {'error': {'message': "
    "'Your token-plan quota has been exhausted.', 'id': "
    "'a6fbbe72-d9b7-431e-aa03-9d8d399e0025', 'type': "
    "'insufficient_quota', 'code': 'insufficient_quota'}}"
)


async def test_run_stream_sanitizes_tokenplan_quota_error_token_and_storage(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    async def fake_call_llm_stream(messages, tools):
        raise RuntimeError(RAW_TOKENPLAN_QUOTA_ERROR)
        if False:  # pragma: no cover - keep this an async generator seam
            yield {}

    executor._call_llm_stream = fake_call_llm_stream

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="我适合怎样的锻炼",
            user_auth_token="test-token",
        )
    ]

    visible_text = "".join(
        event["data"]["content"]
        for event in events
        if event.get("event") == "token"
    )

    assert "insufficient_quota" not in visible_text
    assert "token-plan quota" not in visible_text
    assert "Error code: 429" not in visible_text
    assert "模型额度" in visible_text
    assert "切换模型" in visible_text

    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert "insufficient_quota" not in saved.content
    assert "token-plan quota" not in saved.content
    assert "Error code: 429" not in saved.content
    assert "模型额度" in saved.content


def test_safe_tool_error_message_hides_upstream_details_and_remains_actionable():
    message = safe_tool_error_message(
        "health_record",
        "HTTP 200 status: 200 upstream payload contains request_id=secret-123",
    )

    assert message == "健康记录暂时无法完成，请稍后重试。"
    assert "status: 200" not in message
    assert "secret-123" not in message


def test_safe_tool_error_message_distinguishes_timeout_and_network_failures():
    assert safe_tool_error_message("health_query", TimeoutError("read timed out")) == (
        "健康数据查询处理超时，请稍后重试。"
    )
    assert safe_tool_error_message("health_query", "connection reset by peer") == (
        "健康数据查询暂时无法连接服务，请检查网络后重试。"
    )
