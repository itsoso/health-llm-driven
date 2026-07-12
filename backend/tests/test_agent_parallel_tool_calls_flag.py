# -*- coding: utf-8 -*-
"""LLM_PARALLEL_TOOL_CALLS 旗标 (Phase-2 rank5, ships-OFF)。

锁死:
  1. 关 (默认): _call_llm / _call_llm_stream 发给 provider 的 payload **不含**
     parallel_tool_calls (逐字节不变);
  2. 开 + 携带 tools: payload 带 parallel_tool_calls=True;
  3. 开 + 不携带 tools (pass_tools 假): payload **不带** parallel_tool_calls
     (无 tools 时带该参数会让真实 SDK 报错)。
"""
import pytest

from app.services.agent_executor import AgentExecutor


class _CapProvider:
    """捕获发给 provider 的 kwargs 的假 provider。"""

    model = "qwen3.6-flash"
    provider_name = "tokenplan"

    def __init__(self):
        self.chat_kwargs = None
        self.stream_kwargs = None

    async def chat(self, **kwargs):
        self.chat_kwargs = dict(kwargs)
        return {"content": "ok", "finish_reason": "stop"}

    async def chat_stream(self, **kwargs):
        self.stream_kwargs = dict(kwargs)
        yield {"type": "finish", "finish_reason": "stop"}


_TOOLS = [{"type": "function", "function": {"name": "health_record",
                                            "parameters": {"type": "object", "properties": {}}}}]


def _prep(executor, provider, pass_tools, monkeypatch, *, flag):
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.settings.llm_parallel_tool_calls", flag)
    monkeypatch.setattr(executor, "_resolve_chat_provider", lambda tools: (provider, pass_tools))
    monkeypatch.setattr(executor, "_messages_for_round", lambda msgs: msgs)
    monkeypatch.setattr(executor, "_answer_max_tokens", lambda: 2000)
    monkeypatch.setattr(executor, "_effective_model_is_non_streaming", lambda: False)
    monkeypatch.setattr(executor, "_maybe_apply_synthesis_thinking_budget", lambda sk: None)


async def _drain_stream(executor, messages, tools):
    return [evt async for evt in executor._call_llm_stream(messages, tools)]


# ── 关: payload 逐字节不含 parallel_tool_calls ────────────────────────────────

@pytest.mark.asyncio
async def test_flag_off_chat_has_no_parallel_param(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, _TOOLS, monkeypatch, flag=False)
    await executor._call_llm([{"role": "user", "content": "记录"}], _TOOLS)
    assert "tools" in provider.chat_kwargs
    assert "parallel_tool_calls" not in provider.chat_kwargs


@pytest.mark.asyncio
async def test_flag_off_stream_has_no_parallel_param(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, _TOOLS, monkeypatch, flag=False)
    await _drain_stream(executor, [{"role": "user", "content": "记录"}], _TOOLS)
    assert "tools" in provider.stream_kwargs
    assert "parallel_tool_calls" not in provider.stream_kwargs


# ── 开 + 携带 tools: payload 带 parallel_tool_calls=True ──────────────────────

@pytest.mark.asyncio
async def test_flag_on_with_tools_sets_parallel_true_chat(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, _TOOLS, monkeypatch, flag=True)
    await executor._call_llm([{"role": "user", "content": "记录"}], _TOOLS)
    assert provider.chat_kwargs["parallel_tool_calls"] is True


@pytest.mark.asyncio
async def test_flag_on_with_tools_sets_parallel_true_stream(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, _TOOLS, monkeypatch, flag=True)
    await _drain_stream(executor, [{"role": "user", "content": "记录"}], _TOOLS)
    assert provider.stream_kwargs["parallel_tool_calls"] is True


# ── 开 + 不携带 tools: 绝不带 parallel_tool_calls (无 tools 带会 SDK 报错) ─────

@pytest.mark.asyncio
async def test_flag_on_without_tools_omits_parallel_chat(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, None, monkeypatch, flag=True)  # pass_tools=None
    await executor._call_llm([{"role": "user", "content": "你好"}], [])
    assert "tools" not in provider.chat_kwargs
    assert "parallel_tool_calls" not in provider.chat_kwargs


@pytest.mark.asyncio
async def test_flag_on_without_tools_omits_parallel_stream(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, None, monkeypatch, flag=True)  # pass_tools=None
    await _drain_stream(executor, [{"role": "user", "content": "你好"}], [])
    assert "tools" not in provider.stream_kwargs
    assert "parallel_tool_calls" not in provider.stream_kwargs
