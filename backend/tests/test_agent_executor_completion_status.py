import pytest

from app.models.user_profile import UserProfile
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


@pytest.mark.asyncio
async def test_langbridge_commercial_model_receives_raw_image_parts(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    db.add(UserProfile(user_id=user.id, llm_model_id="gemini-3.1-pro"))
    db.commit()

    executor = AgentExecutor(db)
    captured_messages = []

    async def fake_medical_import(_user_id, _images):
        return None

    async def fake_vision_preprocess(_message, _images):
        return "视觉预处理文本，不应该替代 LangBridge 原图。"

    async def fake_call_llm(messages, tools):
        captured_messages.append(messages)
        return {
            "content": "我看到了图片。",
            "finish_reason": "stop",
        }

    executor._try_import_medical_report_images = fake_medical_import
    executor._analyze_image_with_vision = fake_vision_preprocess
    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="这张照片里是什么食物？",
            images=[{"base64": "YWJjMTIz", "type": "jpeg"}],
            user_auth_token=None,
        )
    ]

    assert events[-1]["event"] == "done"
    first_call = captured_messages[0]
    last_user = next(msg for msg in reversed(first_call) if msg.get("role") == "user")
    assert isinstance(last_user["content"], list)
    assert last_user["content"][0] == {"type": "text", "text": "这张照片里是什么食物？"}
    assert last_user["content"][1]["type"] == "image_url"
    assert last_user["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,YWJjMTIz"
