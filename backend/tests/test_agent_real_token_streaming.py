# -*- coding: utf-8 -*-
"""真 token 流式回归 (feat/agent-real-token-streaming)。

钉三件事:
1. OpenAIProvider.chat_stream 实时 yield content delta + 正确按 index 重组 tool_calls。
2. pii_scrub / usage_tracker 的包装层覆盖 chat_stream —— 流式路径不绕过脱敏 (硬安全边界)。
3. AgentExecutor.run_stream 通过 provider.chat_stream 真流式: 多个 content delta →
   多个 {"event":"token"} 事件; tool-calls-then-text 仍执行工具再流式最终答案。
"""
import json
from types import SimpleNamespace

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.llm.base import LLMProvider
from app.services.llm.providers.openai_provider import OpenAIProvider


# ── 1. OpenAIProvider.chat_stream ─────────────────────────────────────────────


def _chunk(content=None, tool_calls=None, finish_reason=None):
    """构造一个仿 OpenAI streaming chunk。"""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tc_fragment(index, *, id=None, name=None, arguments=None, type=None):
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=id, type=type, function=fn)


class _FakeOpenAIClient:
    """client.chat.completions.create(stream=True) 返回同步迭代器。"""

    def __init__(self, chunks):
        self._chunks = chunks
        self.create_kwargs = None

        completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=completions)

    def _create(self, **kwargs):
        self.create_kwargs = kwargs
        return iter(self._chunks)


async def test_chat_stream_emits_content_deltas_in_real_time(mock_ai_consent_for_provider_protocol):
    chunks = [
        _chunk(content="你好"),
        _chunk(content="，"),
        _chunk(content="今天感觉如何？"),
        _chunk(finish_reason="stop"),
    ]
    provider = OpenAIProvider(api_key="k", model="gpt-test")
    provider._async_client = _FakeOpenAIClient(chunks)

    events = [evt async for evt in provider.chat_stream([{"role": "user", "content": "hi"}])]

    content_texts = [e["text"] for e in events if e["type"] == "content"]
    assert content_texts == ["你好", "，", "今天感觉如何？"]
    assert events[-1] == {"type": "finish", "finish_reason": "stop"}
    # 没有工具时不发 tool_calls 事件
    assert all(e["type"] != "tool_calls" for e in events)


async def test_chat_stream_reassembles_tool_calls_by_index(mock_ai_consent_for_provider_protocol):
    # tool_call 分片跨多个 chunk: id/name 在第一片, arguments 字符串分两片拼接。
    chunks = [
        _chunk(content="我来记录。"),
        _chunk(tool_calls=[_tc_fragment(0, id="call_a", name="health_record", type="function", arguments='{"record')]),
        _chunk(tool_calls=[_tc_fragment(0, arguments='_type":"water"}')]),
        _chunk(finish_reason="tool_calls"),
    ]
    provider = OpenAIProvider(api_key="k", model="gpt-test")
    provider._async_client = _FakeOpenAIClient(chunks)

    events = [evt async for evt in provider.chat_stream([{"role": "user", "content": "记录喝水"}], tools=[{"x": 1}])]

    # content 实时
    assert [e["text"] for e in events if e["type"] == "content"] == ["我来记录。"]
    # tool_calls 重组正确
    tc_events = [e for e in events if e["type"] == "tool_calls"]
    assert len(tc_events) == 1
    tcs = tc_events[0]["tool_calls"]
    assert len(tcs) == 1
    assert tcs[0]["id"] == "call_a"
    assert tcs[0]["function"]["name"] == "health_record"
    assert tcs[0]["function"]["arguments"] == '{"record_type":"water"}'
    assert json.loads(tcs[0]["function"]["arguments"]) == {"record_type": "water"}
    # tools 透传给底层 create()
    assert provider._async_client.create_kwargs["tools"] == [{"x": 1}]
    assert provider._async_client.create_kwargs["stream"] is True
    assert events[-1]["finish_reason"] == "tool_calls"


async def test_chat_stream_reassembles_two_parallel_tool_calls_by_index(mock_ai_consent_for_provider_protocol):
    """Phase-2 rank6 回归: 切到 AsyncOpenAI + async for 后, **多个** index 的 tool_call
    分片仍各自按 index 累积 (parallel_tool_calls=true / rank5 依赖这个)。两个 tool_call
    的 arguments 分片交错到达, 必须按 index 分别拼接、按 index 升序产出。"""
    chunks = [
        _chunk(tool_calls=[_tc_fragment(0, id="c0", name="health_record", type="function", arguments='{"record_type":"water",')]),
        _chunk(tool_calls=[_tc_fragment(1, id="c1", name="health_record", type="function", arguments='{"record_type":')]),
        _chunk(tool_calls=[_tc_fragment(0, arguments='"data":{"amount":500}}')]),
        _chunk(tool_calls=[_tc_fragment(1, arguments='"diet","data":{"food":"苹果"}}')]),
        _chunk(finish_reason="tool_calls"),
    ]
    provider = OpenAIProvider(api_key="k", model="gpt-test")
    provider._async_client = _FakeOpenAIClient(chunks)

    events = [evt async for evt in provider.chat_stream([{"role": "user", "content": "喝了500ml水又吃了个苹果"}], tools=[{"x": 1}])]

    tc_events = [e for e in events if e["type"] == "tool_calls"]
    assert len(tc_events) == 1
    tcs = tc_events[0]["tool_calls"]
    # 两个 tool_call, 按 index 升序。
    assert [tc["id"] for tc in tcs] == ["c0", "c1"]
    assert json.loads(tcs[0]["function"]["arguments"]) == {"record_type": "water", "data": {"amount": 500}}
    assert json.loads(tcs[1]["function"]["arguments"]) == {"record_type": "diet", "data": {"food": "苹果"}}
    assert events[-1]["finish_reason"] == "tool_calls"


# ── 2. base 默认 chat_stream (degraded) ───────────────────────────────────────


class _NonStreamProvider(LLMProvider):
    provider_name = "fake-nonstream"

    def __init__(self, chat_result):
        self._chat_result = chat_result
        self.chat_calls = []

    async def chat(self, messages, **kwargs):
        self.chat_calls.append((messages, kwargs))
        return self._chat_result

    async def chat_with_vision(self, messages, image_url, **kwargs):  # pragma: no cover
        return ""


async def test_base_chat_stream_degrades_to_single_chat_for_text():
    provider = _NonStreamProvider("完整回答")
    events = [e async for e in provider.chat_stream([{"role": "user", "content": "hi"}])]
    assert events[0] == {"type": "content", "text": "完整回答"}
    assert events[-1]["type"] == "finish"
    assert len(provider.chat_calls) == 1
    # 默认实现用 stream=False 调一次 chat
    assert provider.chat_calls[0][1]["stream"] is False


async def test_base_chat_stream_passes_tool_calls_through():
    result = {
        "content": "",
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": "c1", "type": "function",
                        "function": {"name": "health_record", "arguments": "{}"}}],
    }
    provider = _NonStreamProvider(result)
    events = [e async for e in provider.chat_stream([{"role": "user", "content": "记录"}], tools=[{"t": 1}])]
    tc = [e for e in events if e["type"] == "tool_calls"]
    assert tc and tc[0]["tool_calls"][0]["function"]["name"] == "health_record"


# ── 3. pii_scrub / usage_tracker 包装覆盖 chat_stream ─────────────────────────


async def test_pii_scrub_wraps_chat_stream_and_redacts_messages():
    from app.services.llm.pii_scrub import wrap_provider_pii_scrub

    seen_messages = {}

    class _Provider:
        provider_name = "p"

        async def chat(self, messages, **kwargs):  # pragma: no cover
            return ""

        async def chat_with_vision(self, messages, image_url, **kwargs):  # pragma: no cover
            return ""

        async def chat_stream(self, messages, **kwargs):
            seen_messages["messages"] = messages
            yield {"type": "content", "text": "ok"}
            yield {"type": "finish", "finish_reason": "stop"}

    provider = wrap_provider_pii_scrub(_Provider())

    raw = [{"role": "user", "content": "我手机 13800138000 和邮箱 a@b.com"}]
    events = [e async for e in provider.chat_stream(raw)]

    # 底层收到的是脱敏后的消息 —— 流式路径绝不绕过脱敏。
    scrubbed = seen_messages["messages"][0]["content"]
    assert "13800138000" not in scrubbed
    assert "a@b.com" not in scrubbed
    assert "[PHONE]" in scrubbed and "[EMAIL]" in scrubbed
    # 事件仍正常透传
    assert any(e["type"] == "content" and e["text"] == "ok" for e in events)


async def test_usage_tracker_wraps_chat_stream_and_records(monkeypatch):
    import app.services.llm.usage_tracker as tracker

    recorded = {}

    def fake_record_usage(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(tracker, "record_usage", fake_record_usage)

    class _Provider:
        provider_name = "p"
        model = "m-test"

        async def chat(self, messages, **kwargs):  # pragma: no cover
            return ""

        async def chat_with_vision(self, messages, image_url, **kwargs):  # pragma: no cover
            return ""

        async def chat_stream(self, messages, **kwargs):
            yield {"type": "content", "text": "部分一"}
            yield {"type": "content", "text": "部分二"}
            yield {"type": "finish", "finish_reason": "stop"}

    provider = tracker.wrap_provider(_Provider())
    events = [e async for e in provider.chat_stream([{"role": "user", "content": "hi"}])]

    assert [e["text"] for e in events if e["type"] == "content"] == ["部分一", "部分二"]
    # 累积的 completion 文本被记录
    assert recorded["completion_text"] == "部分一部分二"
    assert recorded["model"] == "m-test"
    assert recorded["success"] is True


# ── 4. run_stream 真流式 ──────────────────────────────────────────────────────


async def test_run_stream_emits_multiple_token_events_for_real_streaming(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    deltas = ["根据你的", "睡眠和心率", "建议先保持二区有氧。"]

    async def fake_call_llm_stream(messages, tools):
        for d in deltas:
            yield {"type": "content", "text": d}
        yield {"type": "finish", "finish_reason": "stop"}

    executor._call_llm_stream = fake_call_llm_stream

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message="给我训练建议", user_auth_token=None,
        )
    ]

    token_events = [e for e in events if e.get("event") == "token"]
    token_texts = [e["data"]["content"] for e in token_events]
    # 真流式: 每个 delta 一个 token 事件 (不是一次性整段)。
    assert token_texts == deltas
    assert len(token_events) == len(deltas)
    rendered = "".join(token_texts)
    assert rendered == "".join(deltas)
    assert events[-1]["event"] == "done"
    # 落库的完整回复 = 流式拼接结果
    from app.models.agent_conversation import AgentMessage
    saved = db.query(AgentMessage).filter_by(role="assistant").one()
    assert saved.content == rendered


async def test_run_stream_tool_calls_then_streamed_final_text(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds = []
    executed = []

    async def fake_call_llm_stream(messages, tools):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            # 第一轮: 结构化 tool_calls (无正文)
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "health_query",
                             "arguments": json.dumps({"dimension": "weight", "days": 7})},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            # 第二轮: 真流式最终答案, 多个 delta
            for d in ["体重", "近 7 天", "稳定。"]:
                yield {"type": "content", "text": d}
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append((tool_name, args_raw))
        return json.dumps({"records": [{"date": "2026-05-18", "weight": 71.2}]})

    executor._call_llm_stream = fake_call_llm_stream
    executor._execute_tool = fake_execute_tool

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message="分析我的体重趋势", user_auth_token="test-token",
        )
    ]

    # 工具被执行
    assert executed and executed[0][0] == "health_query"
    assert any(e.get("event") == "tool_call" and e["data"]["tool"] == "health_query" for e in events)
    assert any(e.get("event") == "tool_result" for e in events)
    # 最终答案真流式: 3 个 token 事件
    token_texts = [e["data"]["content"] for e in events if e.get("event") == "token"]
    assert token_texts == ["体重", "近 7 天", "稳定。"]
    assert "".join(token_texts) == "体重近 7 天稳定。"
    assert events[-1]["event"] == "done"
