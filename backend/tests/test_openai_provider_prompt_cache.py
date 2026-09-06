# -*- coding: utf-8 -*-
"""OpenAIProvider 显式上下文缓存透传测试 (Phase-2 rank3, DashScope cache_control)。

锁死:
  1. _maybe_mark_prompt_cache: 没 prompt_cache_markers 键 → 原样返回 messages (同对象);
     有 → 走 apply_cache_markers 变换 + **pop 掉**该键 (它是 OpenAI SDK 不认识的 kwarg,
     顶层传会 TypeError);
  2. chat() / chat_stream() flag 关 (无信号) → 发给底层 create() 的 messages **逐字节不变**
     (string content, 无 cache_control), 且 kwargs 不含 prompt_cache_markers;
  3. flag 开 (prompt_cache_markers=True) → messages 带 cache_control 断点, prompt_cache_markers
     绝不泄漏进 create() 顶层 kwarg;
  4. 与 extra_body / thinking_budget 组合不互相破坏。
"""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("mock_ai_consent_for_provider_protocol")

from app.services.llm.providers.openai_provider import (
    OpenAIProvider,
    _maybe_mark_prompt_cache,
)


def _has_cache_control(msg):
    c = msg.get("content")
    return isinstance(c, list) and c and c[0].get("cache_control") == {"type": "ephemeral"}


# ──── 1. 纯函数 _maybe_mark_prompt_cache ────

def test_no_signal_returns_same_object():
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    kwargs = {"temperature": 0.3}
    out = _maybe_mark_prompt_cache(msgs, kwargs, "qwen3.7-max")
    assert out is msgs  # 逐字节不变: 原对象透传
    assert kwargs == {"temperature": 0.3}


def test_signal_true_marks_and_pops_key():
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    kwargs = {"prompt_cache_markers": True, "temperature": 0.3}
    out = _maybe_mark_prompt_cache(msgs, kwargs, "qwen3.7-max")  # 探针验证模型
    assert _has_cache_control(out[0])            # system 打了断点
    assert "prompt_cache_markers" not in kwargs  # 键被 pop (不会流进 create())
    assert kwargs == {"temperature": 0.3}


def test_signal_dict_layout_threads_knobs():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "q"},
        {"role": "tool", "content": "trailing"},
    ]
    # 只标 tail, 关 system/history_prefix
    kwargs = {"prompt_cache_markers": {"mark_system": False, "mark_history_prefix": False, "mark_tail": True}}
    out = _maybe_mark_prompt_cache(msgs, kwargs, "qwen3.7-max")
    assert not _has_cache_control(out[0])   # system 未标
    assert _has_cache_control(out[2])       # tail 标了
    assert "prompt_cache_markers" not in kwargs


def test_signal_unsupported_model_strips_no_mark():
    # 最后一英里 fail-closed: 非探针验证模型 (failover 到的 MiniMax) 绝不贴 cache_control,
    # 但信号键仍被 pop (不泄漏进 create())。
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    kwargs = {"prompt_cache_markers": True, "temperature": 0.3}
    out = _maybe_mark_prompt_cache(msgs, kwargs, "MiniMax-M2.5")
    assert out is msgs                           # 未标, 原对象透传
    assert not _has_cache_control(out[0])
    assert "prompt_cache_markers" not in kwargs   # 信号仍被 pop
    assert kwargs == {"temperature": 0.3}


def test_signal_unknown_and_none_model_strips_no_mark():
    # 未知模型 / model=None (查不到注册表) → fail-closed 不贴。
    for mid in ("totally-unknown-model", None):
        msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
        kwargs = {"prompt_cache_markers": True}
        out = _maybe_mark_prompt_cache(msgs, kwargs, mid)
        assert out is msgs
        assert "prompt_cache_markers" not in kwargs


# ──── 2. chat(stream=False) ────

def _mock_nonstream_response():
    resp = MagicMock()
    resp.usage = None
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = MagicMock()
    choice.message.tool_calls = None
    choice.message.content = "答案"
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_chat_flag_off_payload_byte_identical():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=_mock_nonstream_response())
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    with patch.object(provider, "_get_client", return_value=mock_client):
        await provider.chat(messages=msgs, stream=False)
    _, kwargs = mock_client.chat.completions.create.call_args
    # 无缓存信号: messages 逐字节不变 (string content), 无 cache_control, 无泄漏键
    assert kwargs["messages"] == msgs
    assert kwargs["messages"][0]["content"] == "SYS"
    assert "prompt_cache_markers" not in kwargs


@pytest.mark.asyncio
async def test_chat_flag_on_injects_cache_control_no_leak():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=_mock_nonstream_response())
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    with patch.object(provider, "_get_client", return_value=mock_client):
        await provider.chat(messages=msgs, stream=False, prompt_cache_markers=True)
    _, kwargs = mock_client.chat.completions.create.call_args
    assert _has_cache_control(kwargs["messages"][0])         # system 断点在
    assert "prompt_cache_markers" not in kwargs              # 绝不泄漏顶层
    assert msgs[0]["content"] == "SYS"                       # 原 messages 未被改


@pytest.mark.asyncio
async def test_chat_cache_and_thinking_budget_coexist():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=_mock_nonstream_response())
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    with patch.object(provider, "_get_client", return_value=mock_client):
        await provider.chat(messages=msgs, stream=False, prompt_cache_markers=True, thinking_budget=512)
    _, kwargs = mock_client.chat.completions.create.call_args
    # extra_body 组合不被缓存注入破坏
    assert kwargs["extra_body"] == {"enable_thinking": True, "thinking_budget": 512}
    assert _has_cache_control(kwargs["messages"][0])
    assert "prompt_cache_markers" not in kwargs
    assert "thinking_budget" not in kwargs


# ──── 3. chat_stream ────

def _mk_chunk(content=None):
    chunk = MagicMock()
    chunk.usage = None
    ch = MagicMock()
    ch.finish_reason = None
    ch.delta = MagicMock()
    ch.delta.content = content
    ch.delta.tool_calls = None
    ch.delta.reasoning_content = None
    ch.delta.model_extra = None
    chunk.choices = [ch]
    return chunk


@pytest.mark.asyncio
async def test_chat_stream_flag_off_payload_byte_identical():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=iter([_mk_chunk("答案")]))
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    with patch.object(provider, "_get_async_client", return_value=mock_client):
        _ = [evt async for evt in provider.chat_stream(messages=msgs)]
    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["messages"] == msgs
    assert kwargs["messages"][0]["content"] == "SYS"
    assert "prompt_cache_markers" not in kwargs


@pytest.mark.asyncio
async def test_chat_stream_flag_on_injects_cache_control_no_leak():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=iter([_mk_chunk("答案")]))
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    with patch.object(provider, "_get_async_client", return_value=mock_client):
        events = [evt async for evt in provider.chat_stream(messages=msgs, prompt_cache_markers=True)]
    assert {"type": "content", "text": "答案"} in events
    _, kwargs = mock_client.chat.completions.create.call_args
    assert _has_cache_control(kwargs["messages"][0])
    assert "prompt_cache_markers" not in kwargs
    assert msgs[0]["content"] == "SYS"  # 原 messages 未被改


# ──── 4. failover 残留洞: 信号被带给不支持显式缓存的 fallback 模型 → 最后一英里 fail-closed ────

@pytest.mark.asyncio
async def test_chat_nonsupporting_fallback_model_no_cache_control():
    # 模拟 executor failover: chat_kwargs 带 prompt_cache_markers=True (按主选 qwen 置)
    # 被原样带给一个**不支持**显式缓存的 fallback provider (MiniMax) → 按实际 use_model
    # 反查注册表 fail-closed, payload 无 cache_control, 信号仍 pop。
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="MiniMax-M2.5")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=_mock_nonstream_response())
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    with patch.object(provider, "_get_client", return_value=mock_client):
        await provider.chat(messages=msgs, stream=False, prompt_cache_markers=True)
    _, kwargs = mock_client.chat.completions.create.call_args
    assert not _has_cache_control(kwargs["messages"][0])   # 非支持模型: 无 cache_control
    assert kwargs["messages"][0]["content"] == "SYS"       # string content 原样
    assert "prompt_cache_markers" not in kwargs


@pytest.mark.asyncio
async def test_chat_stream_nonsupporting_fallback_model_no_cache_control():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="MiniMax-M2.5")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=iter([_mk_chunk("答案")]))
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    with patch.object(provider, "_get_async_client", return_value=mock_client):
        _ = [evt async for evt in provider.chat_stream(messages=msgs, prompt_cache_markers=True)]
    _, kwargs = mock_client.chat.completions.create.call_args
    assert not _has_cache_control(kwargs["messages"][0])
    assert "prompt_cache_markers" not in kwargs
