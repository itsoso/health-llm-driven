"""OpenAIProvider.chat_stream: reasoning_content 增量作为独立事件产出(qwen 思考流)。

背景: qwen3.7-max 合成轮首个可见 token 前有 ~20-34s 纯 reasoning 死气(探针实证
scripts/probe_qwen_thinking_budget.py —— 首个 reasoning delta @ ~1.7s vs 首个 content
@ ~35.8s)。provider 过去只读 delta.content、丢弃 delta.reasoning_content。本测试锁死:

  1. reasoning_content 增量作为 {"type":"reasoning","text":...} 事件产出,与 content 区分;
  2. reasoning 文本绝不并进 content 事件(答案 byte-identical);
  3. model_extra.reasoning_content 兜底形态同样识别;
  4. 无 reasoning 的普通流(非 qwen / 思考关)= 零 reasoning 事件(byte-identical 路径)。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("mock_ai_consent_for_provider_protocol")

from app.services.llm.providers.openai_provider import (
    OpenAIProvider,
    _extract_reasoning_delta,
)


def _delta(content=None, reasoning=None, tool_calls=None, model_extra=None):
    ns = SimpleNamespace(content=content, tool_calls=tool_calls)
    if reasoning is not None:
        ns.reasoning_content = reasoning
    # model_extra 仅在显式给时才设,模拟 SDK 把未知字段落在 model_extra 的形态。
    if model_extra is not None:
        ns.model_extra = model_extra
    return ns


def _chunk(delta, finish_reason=None, usage=None):
    return SimpleNamespace(
        usage=usage,
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)],
    )


async def _collect(provider):
    return [
        evt
        async for evt in provider.chat_stream(
            messages=[{"role": "user", "content": "分析我的状态"}],
        )
    ]


# ──── 纯函数: _extract_reasoning_delta ────

def test_extract_reasoning_from_direct_attr():
    assert _extract_reasoning_delta(_delta(reasoning="先看HRV")) == "先看HRV"


def test_extract_reasoning_from_model_extra():
    d = SimpleNamespace(content=None, tool_calls=None,
                        model_extra={"reasoning_content": "从 model_extra 取"})
    assert _extract_reasoning_delta(d) == "从 model_extra 取"


def test_extract_reasoning_none_when_absent():
    assert _extract_reasoning_delta(_delta(content="答案")) is None
    assert _extract_reasoning_delta(SimpleNamespace(content=None, tool_calls=None)) is None


# ──── chat_stream: reasoning 事件独立于 content ────

@pytest.mark.asyncio
async def test_reasoning_deltas_yield_separate_events_before_content():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    chunks = [
        _chunk(_delta(reasoning="先看 HRV 夜间下滑")),
        _chunk(_delta(reasoning="再对比睡眠结构")),
        _chunk(_delta(content="综合来看,")),
        _chunk(_delta(content="建议补蛋白。")),
        _chunk(_delta(), finish_reason="stop"),
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=iter(chunks))
    with patch.object(provider, "_get_async_client", return_value=mock_client):
        events = await _collect(provider)

    types = [e["type"] for e in events]
    assert types == ["reasoning", "reasoning", "content", "content", "finish"]
    reasoning = [e["text"] for e in events if e["type"] == "reasoning"]
    content = "".join(e["text"] for e in events if e["type"] == "content")
    assert reasoning == ["先看 HRV 夜间下滑", "再对比睡眠结构"]
    # 答案 content 绝不含 reasoning 文本。
    assert content == "综合来看,建议补蛋白。"
    assert "HRV" not in content and "睡眠结构" not in content


@pytest.mark.asyncio
async def test_reasoning_from_model_extra_is_surfaced():
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="qwen3.7-max")
    chunks = [
        _chunk(_delta(model_extra={"reasoning_content": "extra 里的思考"})),
        _chunk(_delta(content="答案")),
        _chunk(_delta(), finish_reason="stop"),
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=iter(chunks))
    with patch.object(provider, "_get_async_client", return_value=mock_client):
        events = await _collect(provider)
    assert {"type": "reasoning", "text": "extra 里的思考"} in events
    assert {"type": "content", "text": "答案"} in events


@pytest.mark.asyncio
async def test_no_reasoning_stream_yields_zero_reasoning_events():
    """非 qwen / 思考关: reasoning_content 恒 None → 零 reasoning 事件(byte-identical)。"""
    provider = OpenAIProvider(api_key="k", base_url="http://x/v1", model="deepseek-v3.2")
    chunks = [
        _chunk(_delta(content="直接")),
        _chunk(_delta(content="回答")),
        _chunk(_delta(), finish_reason="stop"),
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create = MagicMock(return_value=iter(chunks))
    with patch.object(provider, "_get_async_client", return_value=mock_client):
        events = await _collect(provider)
    assert all(e["type"] != "reasoning" for e in events)
    assert [e["type"] for e in events] == ["content", "content", "finish"]
