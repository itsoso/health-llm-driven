"""Assert provider payloads, not just the dormant subset selector."""

import json
from copy import deepcopy

import pytest

from app.services import agent_executor as ae
from app.services.tool_schema_registry import get_health_tools


class CaptureProvider:
    model = "qwen3.8-max"

    def __init__(self):
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return {"content": "查询结果已返回。", "finish_reason": "stop"}

    async def chat_stream(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        yield {"type": "content", "text": "查询结果已返回。"}
        yield {"type": "finish", "finish_reason": "stop"}


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_actual_provider_receives_domain_subset(db, monkeypatch, stream):
    executor = ae.AgentExecutor(db)
    executor._current_turn_user_message = "综合分析我最近的睡眠趋势"
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(ae.settings, "agent_base_url", None)
    monkeypatch.setattr(ae.settings, "agent_api_key", None)
    provider = CaptureProvider()
    monkeypatch.setattr(
        executor, "_resolve_chat_provider", lambda tools: (provider, tools)
    )
    tools = get_health_tools()
    messages = [{"role": "user", "content": executor._current_turn_user_message}]
    if stream:
        _ = [event async for event in executor._call_llm_stream(messages, tools)]
    else:
        await executor._call_llm(messages, tools)
    sent = provider.calls[0]["tools"]
    assert {t["function"]["name"] for t in sent} == set(ae.RECOVERY_TURN_TOOL_NAMES)
    assert len(json.dumps(sent)) < len(json.dumps(tools)) * 0.5
    assert len(tools) == len(
        get_health_tools()
    )  # Pi's authoritative registry is unchanged.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "查询我的饮食和肝功能，调整我的补剂提醒",
        "删除刚才的记录",
        "继续分析刚才那个结果",
        "这个怎么办",
    ],
)
async def test_ambiguous_or_mutating_tasks_keep_authorized_tools(
    db, monkeypatch, query
):
    executor = ae.AgentExecutor(db)
    executor._current_turn_user_message = query
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(ae.settings, "agent_base_url", None)
    monkeypatch.setattr(ae.settings, "agent_api_key", None)
    provider = CaptureProvider()
    monkeypatch.setattr(
        executor, "_resolve_chat_provider", lambda tools: (provider, tools)
    )
    tools = get_health_tools()
    await executor._call_llm([{"role": "user", "content": query}], tools)
    assert provider.calls[0]["tools"] == tools


@pytest.mark.asyncio
async def test_tool_projection_never_restores_removed_tools(db, monkeypatch):
    executor = ae.AgentExecutor(db)
    executor._current_turn_user_message = "综合分析我最近的睡眠趋势"
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(ae.settings, "agent_base_url", None)
    monkeypatch.setattr(ae.settings, "agent_api_key", None)
    provider = CaptureProvider()
    monkeypatch.setattr(
        executor, "_resolve_chat_provider", lambda tools: (provider, tools)
    )
    tools = get_health_tools(subset=["knowledge_search"])
    await executor._call_llm([{"role": "user", "content": "query"}], tools)
    assert provider.calls[0]["tools"] == tools


@pytest.mark.asyncio
async def test_disabled_projection_preserves_payload(db, monkeypatch):
    executor = ae.AgentExecutor(db)
    executor._current_turn_user_message = "综合分析我最近的睡眠趋势"
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", False)
    monkeypatch.setattr(ae.settings, "agent_base_url", None)
    monkeypatch.setattr(ae.settings, "agent_api_key", None)
    provider = CaptureProvider()
    monkeypatch.setattr(
        executor, "_resolve_chat_provider", lambda tools: (provider, tools)
    )
    tools = get_health_tools()
    await executor._call_llm([{"role": "user", "content": "query"}], tools)
    assert provider.calls[0]["tools"] == tools


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,tool_names",
    [
        ("请介绍一下你自己", set()),
        ("杭州今天天气怎么样？", {"environment_check"}),
    ],
)
async def test_public_turn_uses_compact_provider_payload(
    db,
    auth_user_and_headers,
    monkeypatch,
    isolated_agent_protocol_transport,
    query,
    tool_names,
):
    from tests.test_agent_executor_fast_routing import _wire_common
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.decisions import routing

    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="synthetic history")
    svc.save_message(conv.id, "user", "OLD_PRIVATE_HEALTH_SENTINEL")
    provider = CaptureProvider()
    _wire_common(executor, monkeypatch, lambda _: provider)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user", lambda *a, **kw: provider
    )
    monkeypatch.setattr(ae, "get_health_tools", get_health_tools)
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(ae.settings, "decision_mode", "on")

    async def unexpected_decision(*args, **kwargs):
        pytest.fail("A closed public task must not wait for Laya")

    monkeypatch.setattr(routing, "decide_route", unexpected_decision)
    fetched = []

    async def weather_read(check_type, *, city, days):
        fetched.append((check_type, city))
        return {
            "weather": {
                "available": True,
                "city": city,
                "text": "多云",
                "temp": "18",
                "obsTime": "2026-10-04T10:00+08:00",
            }
        }

    monkeypatch.setattr(executor, "_read_environment_in_process", weather_read)
    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            conversation_id=conv.id,
            user_auth_token="test-token",
        )
    ]
    assert events[-1]["event"] == "done"
    assert provider.calls
    for call in provider.calls:
        assert not call.get("tools")  # Public weather reads before a single synthesis.
        payload = json.dumps(call["messages"], ensure_ascii=False)
        assert "OLD_PRIVATE_HEALTH_SENTINEL" not in payload
        assert len(payload) < 2500
    assert len(provider.calls) == 1
    assert fetched == ([("weather", "杭州")] if tool_names else [])
    assert events[-1]["data"]["write_receipts"] == []


@pytest.mark.asyncio
async def test_public_weather_does_not_invent_location(db, monkeypatch):
    executor = ae.AgentExecutor(db)
    executor._public_task = "weather"
    executor._current_user_id = 99999

    async def forbidden_fetch(*args, **kwargs):
        pytest.fail("Missing location must not fetch a default city")

    monkeypatch.setattr(executor, "_read_environment_in_process", forbidden_fetch)
    result = json.loads(
        await executor._exec_environment("http://unused", {}, {"check_type": "weather"})
    )
    assert result["error"] == "location_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [True, False])
async def test_public_weather_http_uses_same_availability_contract(
    db, monkeypatch, available
):
    executor = ae.AgentExecutor(db)
    executor._public_task = "weather"
    monkeypatch.setattr(ae.settings, "reads_in_process", False)

    async def http_weather(url, headers):
        assert url.endswith("/environment/weather?city=%E6%9D%AD%E5%B7%9E")
        return json.dumps(
            {
                "weather": {"available": available, "temperature": 20},
                "exercise_advice": {"advice": "excluded"},
            }
        )

    monkeypatch.setattr(executor, "_api_get", http_weather)
    result = json.loads(
        await executor._exec_environment(
            "http://unused", {}, {"check_type": "weather", "city": "杭州"}
        )
    )
    assert "exercise_advice" not in result
    if available:
        assert result["weather"]["temperature"] == 20
    else:
        assert result["error"] == "weather_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["location_required", "upstream_unavailable"])
async def test_public_weather_failure_is_terminal_without_model(
    db,
    auth_user_and_headers,
    monkeypatch,
    isolated_agent_protocol_transport,
    failure,
):
    from tests.test_agent_executor_fast_routing import _wire_common

    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    provider = CaptureProvider()
    _wire_common(executor, monkeypatch, lambda _: provider)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user", lambda *a, **kw: provider
    )
    monkeypatch.setattr(ae, "get_health_tools", get_health_tools)
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)

    async def failed_weather(*args, **kwargs):
        return json.dumps({"error": failure})

    monkeypatch.setattr(executor, "_exec_environment", failed_weather)
    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id, message="今天天气怎么样？"
        )
    ]
    assert not provider.calls
    from app.models.agent_conversation import AgentMessage

    answer = db.get(AgentMessage, events[-1]["data"]["message_id"]).content
    assert ("哪个城市" if failure == "location_required" else "未完成") in answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,payload",
    [
        (
            "杭州今天天气怎么样？",
            {
                "weather": {"available": False, "temperature": 20, "error": "upstream"},
                "exercise_advice": {"advice": "placeholder"},
            },
        ),
        (
            "杭州明天天气怎么样？",
            {"available": False, "forecasts": [], "source": "unknown"},
        ),
    ],
)
async def test_unavailable_weather_never_sends_placeholder_to_model(
    db,
    auth_user_and_headers,
    monkeypatch,
    isolated_agent_protocol_transport,
    query,
    payload,
):
    from tests.test_agent_executor_fast_routing import _wire_common
    from app.models.agent_conversation import AgentMessage

    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    provider = CaptureProvider()
    _wire_common(executor, monkeypatch, lambda _: provider)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user", lambda *a, **kw: provider
    )
    monkeypatch.setattr(ae, "get_health_tools", get_health_tools)
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)

    async def unavailable(*args, **kwargs):
        return payload

    monkeypatch.setattr(executor, "_read_environment_in_process", unavailable)
    events = [e async for e in executor.run_stream(user_id=user.id, message=query)]
    assert not provider.calls
    answer = db.get(AgentMessage, events[-1]["data"]["message_id"]).content
    assert "未完成" in answer
    assert "20" not in answer


@pytest.mark.asyncio
async def test_public_payload_replay(
    db,
    auth_user_and_headers,
    monkeypatch,
    isolated_agent_protocol_transport,
):
    """Same synthetic turns through real Pi, provider payloads captured at send."""
    import os
    from pathlib import Path
    from tests.test_agent_executor_fast_routing import _wire_common
    from app.services.agent_conversation_service import AgentConversationService

    class WeatherProvider(CaptureProvider):
        async def chat_stream(self, **kwargs):
            self.calls.append(deepcopy(kwargs))
            if "天气" in str(kwargs["messages"][-1].get("content")) and not any(
                m["role"] == "tool" for m in kwargs["messages"]
            ):
                yield {
                    "type": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "weather_1",
                            "type": "function",
                            "function": {
                                "name": "environment_check",
                                "arguments": json.dumps(
                                    {"check_type": "weather", "city": "杭州"}
                                ),
                            },
                        }
                    ],
                }
                yield {"type": "finish", "finish_reason": "tool_calls"}
            else:
                yield {"type": "content", "text": "本次结果已提供。"}
                yield {"type": "finish", "finish_reason": "stop"}

    user, _ = auth_user_and_headers
    results = []
    live_payloads = []
    for query in ("杭州今天天气怎么样？", "请介绍一下你自己"):
        pair = []
        for enabled in (False, True):
            executor = ae.AgentExecutor(db)
            provider = WeatherProvider()
            original_prompt = executor._build_system_prompt
            _wire_common(executor, monkeypatch, lambda _: provider)
            monkeypatch.setattr(executor, "_build_system_prompt", original_prompt)
            monkeypatch.setattr(
                executor, "_build_system_knowledge_prompt_context", lambda *a: ""
            )
            monkeypatch.setattr(
                "app.services.llm.factory.create_provider_for_user",
                lambda *a, **kw: provider,
            )
            monkeypatch.setattr(ae, "get_health_tools", get_health_tools)
            monkeypatch.setattr(ae.settings, "domain_prompt_optimization", enabled)
            monkeypatch.setattr(ae.settings, "decision_mode", "off")

            async def weather(*args, **kwargs):
                return {
                    "weather": {
                        "available": True,
                        "city": "杭州",
                        "text": "多云",
                        "temp": "18",
                        "obsTime": "2026-10-04T10:00+08:00",
                    }
                }

            monkeypatch.setattr(executor, "_read_environment_in_process", weather)
            svc = AgentConversationService(db)
            conv = svc.get_or_create_conversation(
                user.id, None, title="synthetic replay"
            )
            svc.save_message(conv.id, "user", "之前的健康资料仅为合成测试背景。")
            events = [
                e
                async for e in executor.run_stream(
                    user_id=user.id, message=query, conversation_id=conv.id
                )
            ]
            assert events[-1]["event"] == "done"
            assert events[-1]["data"]["completion_status"] == "complete"
            chars = sum(
                len(
                    json.dumps(
                        {"messages": c["messages"], "tools": c.get("tools", [])},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                for c in provider.calls
            )
            pair.append(
                {
                    "enabled": enabled,
                    "calls": len(provider.calls),
                    "payload_chars": chars,
                    "tool_counts": [len(c.get("tools", [])) for c in provider.calls],
                }
            )
            live_payloads.append(
                {
                    "case": "weather" if "天气" in query else "introduction",
                    "enabled": enabled,
                    "calls": provider.calls,
                }
            )
        assert pair[1]["payload_chars"] < pair[0]["payload_chars"] * 0.7
        assert pair[1]["calls"] == 1
        results.append(
            {
                "case": "weather" if "天气" in query else "introduction",
                "measurements": pair,
            }
        )
    if output := os.environ.get("REVA_PROMPT_REPLAY_OUTPUT"):
        Path(output).write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n"
        )
    if output := os.environ.get("REVA_PROMPT_LIVE_PAYLOADS"):
        Path(output).write_text(
            json.dumps(live_payloads, ensure_ascii=False, indent=2) + "\n"
        )
