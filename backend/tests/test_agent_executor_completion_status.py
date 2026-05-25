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
async def test_agent_call_llm_omits_empty_tools_for_commercial_retries(db, auth_user_and_headers, monkeypatch):
    """Empty no-tool retry must not send tools=[] to OpenAI-compatible gateways."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    captured_kwargs = []

    class FakeProvider:
        async def chat(self, **kwargs):
            captured_kwargs.append(kwargs)
            return {"content": "ok", "finish_reason": "stop"}

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        lambda _user_id, _db: FakeProvider(),
    )
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)

    await executor._call_llm([{"role": "user", "content": "请直接回答"}], [])

    assert "tools" not in captured_kwargs[0]


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
async def test_agent_stream_injects_mac_desktop_markdown_instruction(db, auth_user_and_headers, monkeypatch):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *_args, **_kwargs: "你是健康助理。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *_args, **_kwargs: "")

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        return {"content": "## 关键结论\n\n- 已按桌面端 Markdown 输出。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="分析最近饮食趋势",
            user_auth_token=None,
            extra_context=json.dumps({
                "client": "mac",
                "desktop_markdown_response_instruction": "请用 Markdown 分段，不要输出密集长段落。",
            }),
        )
    ]

    system_prompt = calls[0]["messages"][0]["content"]
    assert "## 桌面端回复格式要求" in system_prompt
    assert "请用 Markdown 分段" in system_prompt
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_agent_stream_compacts_context_after_repeated_empty_visible_reply(db, auth_user_and_headers, monkeypatch):
    """Commercial gateways can return stop+empty for long system prompts."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    monkeypatch.setattr(
        executor,
        "_build_system_prompt",
        lambda *_args, **_kwargs: (
            "你是健康助理。\n"
            "## 用户健康档案\n"
            + ("睡眠、血压、运动、饮食和基因风险需要综合评估。\n" * 260)
        ),
    )
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *_args, **_kwargs: "")

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) <= 2:
            return {"content": "", "finish_reason": "stop"}
        return {"content": "压缩上下文后回答：先关注睡眠、血压和今天的第一项任务。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="为什么今天优先这五件任务？",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "压缩上下文后回答" in rendered
    assert len(calls) == 3
    assert calls[2]["tool_count"] == 0
    assert len(calls[2]["messages"][0]["content"]) < len(calls[0]["messages"][0]["content"])
    assert "## 用户健康档案" in calls[2]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_agent_stream_falls_back_to_stable_provider_when_compact_retry_is_empty(db, auth_user_and_headers, monkeypatch):
    """If the selected commercial model keeps returning empty, use a stable fallback."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    fallback_calls = []

    monkeypatch.setattr(
        executor,
        "_build_system_prompt",
        lambda *_args, **_kwargs: (
            "你是健康助理。\n"
            "## 用户健康档案\n"
            + ("睡眠、血压、运动、饮食和基因风险需要综合评估。\n" * 260)
        ),
    )
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *_args, **_kwargs: "")

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        return {"content": "", "finish_reason": "stop"}

    async def fake_fallback(messages):
        fallback_calls.append(messages)
        return {"content": "稳定模型兜底回答：先处理血压、睡眠和低风险运动。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm
    executor._call_llm_fallback_provider = fake_fallback

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="为什么今天优先这五件任务？",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "稳定模型兜底回答" in rendered
    assert len(calls) == 3
    assert len(fallback_calls) == 1
    assert fallback_calls[0][0]["role"] == "system"


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
        and event["data"]["result"] == '{"id":701,"food_items":"鳕鱼 100g + 米饭 150g + 青菜 100g","calories":520}'
        for event in events
    )
    assert "已记录晚餐" in rendered
    assert '"name":"health_record"' not in rendered


@pytest.mark.asyncio
async def test_agent_stream_falls_back_to_tool_result_when_model_synthesis_is_empty(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_record_diet",
                        "type": "function",
                        "function": {
                            "name": "health_record",
                            "arguments": json.dumps({
                                "record_type": "diet",
                                "data": {
                                    "meal_type": "breakfast",
                                    "food_items": "两个豆腐包子",
                                },
                            }, ensure_ascii=False),
                        },
                    },
                ],
            }
        return {"content": "", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        args = json.loads(args_raw)
        assert tool_name == "health_record"
        return json.dumps({
            "message": "已记录早餐：两个豆腐包子",
            "record_type": args["record_type"],
            "food_items": args["data"]["food_items"],
        }, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录饮食 早餐两个豆腐包子",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "已记录早餐：两个豆腐包子" in rendered
    assert "没有收到模型的有效回复" not in rendered
    assert events[-1]["event"] == "done"


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
