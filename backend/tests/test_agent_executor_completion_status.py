import pytest

from app.models.openclaw import OpenClawMessage
from app.services.agent_executor import (
    INTERRUPTED_COMPLETION_NOTICE,
    AgentExecutor,
    _completion_status_from_finish_reason,
)


def test_completion_status_marks_length_finish_reason_as_interrupted():
    assert _completion_status_from_finish_reason("length") == "interrupted"


def test_completion_status_marks_stop_finish_reason_as_complete():
    assert _completion_status_from_finish_reason("stop") == "complete"


@pytest.mark.asyncio
async def test_agent_stream_marks_length_limited_answer_as_interrupted(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    async def fake_call_llm(messages, tools):
        return {
            "content": "## 检查计划\n| 时间 | 行动 |\n| **报",
            "finish_reason": "length",
        }

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="给我一份完整检查计划",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = events[-1]
    saved = db.query(OpenClawMessage).filter_by(role="assistant").one()

    assert INTERRUPTED_COMPLETION_NOTICE in rendered
    assert done["event"] == "done"
    assert done["data"]["completion_status"] == "interrupted"
    assert done["data"]["finish_reason"] == "length"
    assert saved.meta["completion_status"] == "interrupted"
    assert saved.meta["finish_reason"] == "length"
