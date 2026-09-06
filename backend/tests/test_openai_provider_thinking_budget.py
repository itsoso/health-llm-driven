"""OpenAIProvider thinking-budget 透传测试(qwen DashScope enable_thinking / thinking_budget)。

背景: qwen3.7-max 合成轮的隐藏思考阶段吃掉 ~20-36s in-call TTFT。DashScope
compatible-mode 支持 enable_thinking=false / thinking_budget=N 经 extra_body 顶层放置
封顶思考(探针实证见 scripts/probe_qwen_thinking_budget.py)。本测试锁死:
  1. _apply_thinking_controls 把这两个参数正确折进 extra_body(而非当顶层 kwarg);
  2. 没这两个键时零影响(不凭空造 extra_body);
  3. chat() / chat_stream() 真的把 extra_body 传给底层 client.create(),
     且**不**把 thinking_budget/enable_thinking 作为未知顶层 kwarg 泄漏(会 TypeError)。
"""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("mock_ai_consent_for_provider_protocol")

from app.services.llm.providers.openai_provider import (
    OpenAIProvider,
    _apply_thinking_controls,
)


# ──── 1. 纯函数: _apply_thinking_controls ────

def test_no_thinking_keys_is_noop():
    assert _apply_thinking_controls({}) == {}
    assert _apply_thinking_controls({"temperature": 0.3}) == {"temperature": 0.3}
    # 没这两个键时绝不凭空造 extra_body
    assert "extra_body" not in _apply_thinking_controls({"tools": []})


def test_thinking_budget_folds_into_extra_body_and_implies_enable():
    out = _apply_thinking_controls({"thinking_budget": 512})
    assert "thinking_budget" not in out  # 不再当顶层 kwarg
    assert out["extra_body"] == {"enable_thinking": True, "thinking_budget": 512}


def test_enable_thinking_false_folds_into_extra_body():
    out = _apply_thinking_controls({"enable_thinking": False})
    assert "enable_thinking" not in out
    assert out["extra_body"] == {"enable_thinking": False}


def test_thinking_controls_preserve_caller_extra_body():
    out = _apply_thinking_controls(
        {"thinking_budget": 256, "extra_body": {"foo": "bar"}}
    )
    assert out["extra_body"] == {"foo": "bar", "enable_thinking": True, "thinking_budget": 256}


def test_explicit_enable_thinking_false_wins_over_budget_default():
    # 同时给 enable_thinking=False 和 thinking_budget: enable_thinking 显式值不被覆盖
    out = _apply_thinking_controls({"enable_thinking": False, "thinking_budget": 512})
    assert out["extra_body"]["enable_thinking"] is False
    assert out["extra_body"]["thinking_budget"] == 512


def test_thinking_budget_coerced_to_int():
    out = _apply_thinking_controls({"thinking_budget": "512"})
    assert out["extra_body"]["thinking_budget"] == 512


# ──── 2. chat(stream=False): extra_body 真传到 client.create, 无顶层泄漏 ────

def _mock_nonstream_response():
    resp = MagicMock()
    resp.usage = None
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = MagicMock()
    choice.message.tool_calls = None
    choice.message.content = "综合建议…"
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_chat_threads_thinking_budget_into_extra_body():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=_mock_nonstream_response())
    with patch.object(provider, "_get_client", return_value=mock_client):
        out = await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
            thinking_budget=512,
        )
    assert out == "综合建议…"
    _, kwargs = mock_client.chat.completions.create.call_args
    # thinking_budget/enable_thinking 绝不作为顶层 kwarg(会让真实 SDK TypeError)
    assert "thinking_budget" not in kwargs
    assert "enable_thinking" not in kwargs
    assert kwargs["extra_body"] == {"enable_thinking": True, "thinking_budget": 512}


@pytest.mark.asyncio
async def test_chat_without_thinking_budget_sends_no_extra_body():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=_mock_nonstream_response())
    with patch.object(provider, "_get_client", return_value=mock_client):
        await provider.chat(messages=[{"role": "user", "content": "hi"}], stream=False)
    _, kwargs = mock_client.chat.completions.create.call_args
    assert "extra_body" not in kwargs


# ──── 3. chat_stream: extra_body 真传, reasoning delta 不会误当 content ────

@pytest.mark.asyncio
async def test_chat_stream_threads_thinking_budget_into_extra_body():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")

    def _mk_chunk(content=None):
        chunk = MagicMock()
        chunk.usage = None
        ch = MagicMock()
        ch.finish_reason = None
        ch.delta = MagicMock()
        ch.delta.content = content
        ch.delta.tool_calls = None
        chunk.choices = [ch]
        return chunk

    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=iter([_mk_chunk("答案")]))
    # chat_stream 走异步客户端 (Phase-2 rank6);patch _get_async_client。
    with patch.object(provider, "_get_async_client", return_value=mock_client):
        events = [
            evt
            async for evt in provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                thinking_budget=512,
            )
        ]
    assert {"type": "content", "text": "答案"} in events
    _, kwargs = mock_client.chat.completions.create.call_args
    assert "thinking_budget" not in kwargs
    assert kwargs["extra_body"] == {"enable_thinking": True, "thinking_budget": 512}
