import json
from datetime import date, timedelta

import pytest

from app.models.blood_pressure import BloodPressureRecord
from app.models.user_profile import UserProfile
from app.models.openclaw import OpenClawMessage
from app.services.agent_executor import (
    INTERRUPTED_COMPLETION_NOTICE,
    AgentExecutor,
    _completion_status_from_finish_reason,
)


def _stream_from(fake_call_llm):
    """把旧式 fake_call_llm(messages, tools) -> dict 适配成 run_stream 现在用的
    _call_llm_stream(messages, tools) -> AsyncIterator[event]。

    run_stream 第一轮走 _call_llm_stream (真流式 seam); 空回复重试/兜底仍走
    _call_llm。共用同一个 fake_call_llm 保证调用计数序列不变。
    """
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


def test_completion_status_marks_length_finish_reason_as_interrupted():
    assert _completion_status_from_finish_reason("length") == "interrupted"


def test_completion_status_marks_stop_finish_reason_as_complete():
    assert _completion_status_from_finish_reason("stop") == "complete"


@pytest.mark.asyncio
async def test_health_query_blood_pressure_uses_existing_records_endpoint(db):
    executor = AgentExecutor(db)
    captured_urls = []

    async def fake_api_get(url, headers):
        captured_urls.append(url)
        return "[]"

    executor._api_get = fake_api_get

    await executor._exec_health_query(
        "http://testserver/api/v1",
        {},
        {"dimension": "blood_pressure", "days": 7},
    )

    assert captured_urls == ["http://testserver/api/v1/blood-pressure/records/me?limit=10"]


@pytest.mark.asyncio
async def test_query_lab_indicators_bridges_blood_pressure_alias_to_standardized_vitals(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    db.add_all([
        BloodPressureRecord(
            user_id=user.id,
            record_date=date.today(),
            systolic=119,
            diastolic=75,
            pulse=64,
        ),
        BloodPressureRecord(
            user_id=user.id,
            record_date=date.today() - timedelta(days=1),
            systolic=124,
            diastolic=78,
            pulse=66,
        ),
    ])
    db.commit()

    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    result = await executor._exec_query_lab_indicators(
        "",
        {},
        {
            "name": "血压",
            "since": (date.today() - timedelta(days=30)).isoformat(),
            "limit": 10,
        },
    )
    payload = json.loads(result)

    assert payload["metric_key"] == "blood_pressure"
    assert payload["count"] == 2
    assert payload["items"][0]["name"] == "血压"
    assert payload["items"][0]["name_en"] == "BP"
    assert payload["items"][0]["value"] == "119/75"
    assert payload["items"][0]["unit"] == "mmHg"
    assert payload["items"][0]["systolic"] == 119
    assert payload["items"][0]["diastolic"] == 75
    assert payload["items"][0]["pulse"] == 64


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
async def test_agent_call_llm_routes_pure_record_turns_to_fast_model(db, auth_user_and_headers, monkeypatch):
    """Pure record turns should not pay Qwen reasoning latency for tool extraction."""
    user, _headers = auth_user_and_headers
    db.add(UserProfile(user_id=user.id, llm_model_id="qwen3.6-plus"))
    db.commit()

    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._prefer_fast_record_model = True
    created_model_ids = []
    captured_messages = []

    class FakeProvider:
        model = "glm-5"

        async def chat(self, **kwargs):
            captured_messages.append(kwargs["messages"])
            return {"content": "ok", "finish_reason": "stop"}

    def fake_create_provider_for_model_id(model_id):
        created_model_ids.append(model_id)
        return FakeProvider()

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        fake_create_provider_for_model_id,
    )
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)

    await executor._call_llm([{"role": "user", "content": "记录晚餐牛肉饭"}], [])

    assert created_model_ids == ["glm-5"]
    assert executor._last_provider_model_name == "glm-5"
    assert len(captured_messages[0]) == 2
    assert "健康记录工具路由器" in captured_messages[0][0]["content"]
    assert captured_messages[0][1]["content"] == "记录晚餐牛肉饭"


@pytest.mark.asyncio
async def test_agent_stream_finishes_pure_record_turn_from_tool_result(db, auth_user_and_headers):
    """Pure record turns should not spend another LLM round synthesizing success text."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
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
                                "meal_type": "dinner",
                                "food_items": "牛肉饭",
                            },
                        }, ensure_ascii=False),
                    },
                },
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_record"
        return json.dumps({"message": "已记录晚餐：牛肉饭"}, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录晚餐牛肉饭",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert len(calls) == 1
    assert "已记录晚餐：牛肉饭" in rendered
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_agent_stream_auto_confirms_fast_record_tool_calls(db, auth_user_and_headers):
    """Fast record turns should complete simple logging without a second confirmation round."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executed_args = []

    async def fake_call_llm(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call_record_water",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "water",
                            "data": {"amount": 1000},
                        }, ensure_ascii=False),
                    },
                },
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_record"
        parsed = json.loads(args_raw)
        executed_args.append(parsed)
        if parsed.get("confirmed") is not True:
            return (
                "[NEEDS_CONFIRMATION] 我准备记录: 喝水 1000ml. "
                "请向用户复述并问一次'是这样吗？'"
            )
        return json.dumps({"message": "已记录饮水 1000ml"}, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录饮水1000",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert executed_args[0]["confirmed"] is True
    assert executed_args[0]["data"]["confirmed"] is True
    assert "已记录饮水 1000ml" in rendered
    assert "NEEDS_CONFIRMATION" not in rendered
    assert "请向用户复述" not in rendered


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
    executor._call_llm_stream = _stream_from(fake_call_llm)

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
    executor._call_llm_stream = _stream_from(fake_call_llm)

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
    executor._call_llm_stream = _stream_from(fake_call_llm)

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
    executor._call_llm_stream = _stream_from(fake_call_llm)

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
    executor._call_llm_stream = _stream_from(fake_call_llm)
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
        return '{"message":"已删除最后一条饮食记录","record_id":625}'

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
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
        # Real health_record returns a `message` the fast-record path renders.
        return (
            '{"id":701,"message":"已记录晚餐：约 520 kcal，蛋白质 32g",'
            '"food_items":"鳕鱼 100g + 米饭 150g + 青菜 100g","calories":520}'
        )

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
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
        and event["data"]["result"] == (
            '{"id":701,"message":"已记录晚餐：约 520 kcal，蛋白质 32g",'
            '"food_items":"鳕鱼 100g + 米饭 150g + 青菜 100g","calories":520}'
        )
        for event in events
    )
    assert "已记录晚餐" in rendered
    assert '"name":"health_record"' not in rendered


@pytest.mark.asyncio
async def test_agent_stream_strips_leading_inline_tool_json_then_prose(db, auth_user_and_headers):
    """Regression: weaker fast-record models emit the tool-call JSON FIRST and a
    human-readable confirmation/analysis AFTER it. Previously the inline extractor
    bailed on any trailing text, so the raw JSON leaked to the user AND the tool
    never ran (the '已记录' was a hallucination, data not saved). Now the call must
    be recovered+executed and the JSON must never render."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    executed = []

    async def fake_call_llm(messages, tools):
        calls.append(1)
        if len(calls) == 1:
            # JSON first, then prose (mirrors the reported voice-chat screenshot).
            return {
                "content": (
                    '{"name":"health_record","parameters":{"record_type":"symptom","data":{'
                    '"symptom":"口腔溃疡","location":"右嘴角 + 上颚外嘴唇连接处","count":2,'
                    '"severity":4}}} '
                    "已记录：口腔溃疡 ×2（右嘴角、上颚外嘴唇连接处）\n\n原因分析（结合你的基因+近况）..."
                ),
                "finish_reason": "stop",
            }
        # Any follow-up synthesis turn (non-fast-record path) returns clean text.
        return {"content": "已记录：口腔溃疡 ×2。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append((tool_name, json.loads(args_raw)))
        return json.dumps(
            {"message": "已记录：口腔溃疡 ×2", "record_type": "symptom"},
            ensure_ascii=False,
        )

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="右嘴角有口腔溃疡然后上颚外嘴唇连接处有口腔溃疡",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    # 1) the tool actually executed → data persisted (not a hallucinated 已记录)
    assert executed and executed[0][0] == "health_record"
    assert executed[0][1]["record_type"] == "symptom"
    # 2) the raw tool-call JSON never leaks into the visible reply
    assert '"name":"health_record"' not in rendered
    assert '"parameters"' not in rendered
    assert "record_type" not in rendered
    # 3) the user still sees a confirmation
    assert "已记录" in rendered


@pytest.mark.asyncio
async def test_record_intent_with_no_tool_executed_is_flagged(db, auth_user_and_headers):
    """#3 guard: a record-intent turn where the model only SAYS '已记录' but calls no
    tool must be flagged (record_intent_no_tool=True) so silent data loss is observable
    instead of looking like success."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executed = []

    async def fake_call_llm(messages, tools):
        # No tool_calls, no inline JSON — the model hallucinates a successful record.
        return {"content": "已记录晚餐：牛肉饭。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append(tool_name)
        return "{}"

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id, message="记录晚餐 牛肉饭", user_auth_token="test-token",
        )
    ]

    done = [e for e in events if e.get("event") == "done"]
    assert done, "should yield a done event"
    assert done[0]["data"]["record_intent_no_tool"] is True
    assert executed == []  # confirms no tool ran — the flag caught real silent loss


@pytest.mark.asyncio
async def test_record_intent_with_tool_executed_is_not_flagged(db, auth_user_and_headers):
    """Counterpart: when a record turn actually executes a write tool, the guard stays
    off (record_intent_no_tool=False)."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append(1)
        if len(calls) == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps(
                            {"record_type": "diet", "data": {"meal_type": "dinner", "food_items": "牛肉饭"}},
                            ensure_ascii=False,
                        ),
                    },
                }],
            }
        return {"content": "已记录晚餐。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        return json.dumps({"message": "已记录晚餐：牛肉饭"}, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id, message="记录晚餐 牛肉饭", user_auth_token="test-token",
        )
    ]

    done = [e for e in events if e.get("event") == "done"]
    assert done and done[0]["data"]["record_intent_no_tool"] is False


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
    executor._call_llm_stream = _stream_from(fake_call_llm)
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
    executor._call_llm_stream = _stream_from(fake_call_llm)

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
