import json

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
async def test_agent_stream_retries_when_model_returns_empty_visible_reply(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) == 1:
            return {"content": "", "finish_reason": "stop"}
        return {"content": "补发回答：基于 9p21 和运动数据，先保持二区有氧。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="针对我的 9p21 基因，给我未来 30 天方案",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "补发回答" in rendered
    assert calls[-1]["tool_count"] == 0
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_agent_stream_executes_inline_tool_json_instead_of_rendering_it(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    executed = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) == 1:
            return {
                "content": (
                    "好的，我来帮你删除最后一条饮食记录。\n"
                    '{"name":"health_manage","parameters":{"record_type":"diet","operation":"delete","record_id":625}}'
                ),
                "finish_reason": "stop",
            }
        return {"content": "已删除最后一条饮食记录。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append((tool_name, args_raw, user_token))
        return '{"message":"删除成功","record_id":625}'

    executor._call_llm = fake_call_llm
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="删除最后一条饮食记录",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert executed == [
        ("health_manage", '{"record_type": "diet", "operation": "delete", "record_id": 625}', "test-token")
    ]
    assert any(event.get("event") == "tool_call" and event["data"]["tool"] == "health_manage" for event in events)
    assert "已删除最后一条饮食记录" in rendered
    assert '"name":"health_manage"' not in rendered


@pytest.mark.asyncio
async def test_agent_stream_executes_inline_diet_record_json_with_nutrition(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executed = []

    async def fake_call_llm(messages, tools):
        if not executed:
            return {
                "content": (
                    "我先识别并记录这顿饭。\n"
                    '{"name":"health_record","parameters":{"record_type":"diet","data":{'
                    '"meal_type":"dinner","food_items":"鳕鱼 100g + 米饭 150g + 青菜 100g",'
                    '"calories":520,"protein":32,"carbs":58,"fat":14,"fiber":5}}}'
                ),
                "finish_reason": "stop",
            }
        return {"content": "已记录晚餐：约 520 kcal，蛋白质 32g。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        args = json.loads(args_raw)
        executed.append((tool_name, args))
        return '{"id":701,"food_items":"鳕鱼 100g + 米饭 150g + 青菜 100g","calories":520}'

    executor._call_llm = fake_call_llm
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="计算热量和营养并记录饮食",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert executed[0][0] == "health_record"
    assert executed[0][1]["record_type"] == "diet"
    assert executed[0][1]["data"]["protein"] == 32
    assert any(
        event.get("event") == "tool_result"
        and event["data"]["record_type"] == "diet"
        and event["data"]["record_data"]["calories"] == 520
        for event in events
    )
    assert "已记录晚餐" in rendered
    assert '"name":"health_record"' not in rendered


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
