# -*- coding: utf-8 -*-
"""LLM_EXPLICIT_PROMPT_CACHE 旗标 (Phase-2 rank3, ships-OFF)。

锁死 agent_executor 的**门控**层 (provider 侧注入另有 test_openai_provider_prompt_cache):
  1. 关 (默认): _call_llm / _call_llm_stream 发给 provider 的 payload **不含**
     prompt_cache_markers (逐字节不变);
  2. 开 + 模型 supports_explicit_cache=True: payload 带 prompt_cache_markers=True;
  3. 开 + 模型 supports_explicit_cache=False (未探针验证): **不**带 (fail-closed, 免端点拒);
  4. 开 + 无 effective model_id: 不带 (fail-closed)。
"""
import pytest

from app.services.agent_executor import AgentExecutor


class _CapProvider:
    """捕获发给 provider 的 kwargs 的假 provider。"""

    model = "qwen3.7-max"
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


class _FakeEntry:
    def __init__(self, supports: bool):
        self.supports_explicit_cache = supports


def _prep(executor, provider, monkeypatch, *, flag, model_id, supports):
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        "app.services.agent_executor.settings.llm_explicit_prompt_cache", flag
    )
    monkeypatch.setattr(executor, "_resolve_chat_provider", lambda tools: (provider, None))
    monkeypatch.setattr(executor, "_messages_for_round", lambda msgs: msgs)
    monkeypatch.setattr(executor, "_answer_max_tokens", lambda: 2000)
    monkeypatch.setattr(executor, "_effective_model_is_non_streaming", lambda: False)
    monkeypatch.setattr(executor, "_maybe_apply_synthesis_thinking_budget", lambda sk: None)
    # get_model 是方法内部 import 的 → patch 其源模块。
    entry = None if model_id is None else _FakeEntry(supports)
    monkeypatch.setattr(
        "app.services.llm.model_registry.get_model", lambda mid: entry
    )
    executor._last_effective_model_id = model_id


async def _drain_stream(executor, messages):
    return [evt async for evt in executor._call_llm_stream(messages, [])]


_MSGS = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "你好"}]


# ── 关: payload 逐字节不含 prompt_cache_markers ──────────────────────────────

@pytest.mark.asyncio
async def test_flag_off_chat_no_cache_signal(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, monkeypatch, flag=False, model_id="qwen3.7-max", supports=True)
    await executor._call_llm(_MSGS, [])
    assert "prompt_cache_markers" not in provider.chat_kwargs


@pytest.mark.asyncio
async def test_flag_off_stream_no_cache_signal(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, monkeypatch, flag=False, model_id="qwen3.7-max", supports=True)
    await _drain_stream(executor, _MSGS)
    assert "prompt_cache_markers" not in provider.stream_kwargs


# ── 开 + 模型验证过: payload 带 prompt_cache_markers=True ─────────────────────

@pytest.mark.asyncio
async def test_flag_on_supported_model_sets_signal_chat(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, monkeypatch, flag=True, model_id="qwen3.7-max", supports=True)
    await executor._call_llm(_MSGS, [])
    assert provider.chat_kwargs["prompt_cache_markers"] is True


@pytest.mark.asyncio
async def test_flag_on_supported_model_sets_signal_stream(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, monkeypatch, flag=True, model_id="qwen3.7-max", supports=True)
    await _drain_stream(executor, _MSGS)
    assert provider.stream_kwargs["prompt_cache_markers"] is True


# ── 开 + 模型未验证 (supports=False): fail-closed 不带 ────────────────────────

@pytest.mark.asyncio
async def test_flag_on_unverified_model_omits_signal_chat(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, monkeypatch, flag=True, model_id="qwen3.6-flash", supports=False)
    await executor._call_llm(_MSGS, [])
    assert "prompt_cache_markers" not in provider.chat_kwargs


@pytest.mark.asyncio
async def test_flag_on_unverified_model_omits_signal_stream(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, monkeypatch, flag=True, model_id="qwen3.6-flash", supports=False)
    await _drain_stream(executor, _MSGS)
    assert "prompt_cache_markers" not in provider.stream_kwargs


# ── 开 + 无 effective model_id: fail-closed 不带 ─────────────────────────────

@pytest.mark.asyncio
async def test_flag_on_no_model_id_omits_signal(db, monkeypatch):
    executor = AgentExecutor(db)
    provider = _CapProvider()
    _prep(executor, provider, monkeypatch, flag=True, model_id=None, supports=True)
    await executor._call_llm(_MSGS, [])
    assert "prompt_cache_markers" not in provider.chat_kwargs


# ── failover 端到端: 主选 qwen 置信号 → 主选失败 → fallback 到不支持模型 → 该模型 payload 无 cache_control ──

def _mock_nonstream_response():
    from unittest.mock import MagicMock

    resp = MagicMock()
    resp.usage = None
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = MagicMock()
    choice.message.tool_calls = None
    choice.message.content = "ok"
    resp.choices = [choice]
    return resp


class _FailingPrimary:
    model = "qwen3.7-max"
    provider_name = "tokenplan"

    async def chat(self, **kwargs):
        raise RuntimeError("primary down")


@pytest.mark.asyncio
async def test_fallback_to_nonsupporting_model_no_cache_control(db, monkeypatch):
    """coordinator 要求的场景: flag on + 主选 qwen3.7-max (supported) 置了 markers 信号,
    主选 chat() 抛错 → executor failover 到**不支持**显式缓存的 fallback (MiniMax) →
    该 fallback 的真实 create() payload **无** cache_control (provider 最后一英里 fail-closed)。"""
    from unittest.mock import MagicMock, patch
    from app.services.llm.providers.openai_provider import OpenAIProvider

    executor = AgentExecutor(db)
    primary = _FailingPrimary()
    # 真实 fallback provider = MiniMax (注册表默认 supports_explicit_cache=False), mock client
    fb = OpenAIProvider(api_key="k", base_url="http://x/v1", model="MiniMax-M2.5")
    fb_client = MagicMock()
    fb_client.chat.completions.create = MagicMock(return_value=_mock_nonstream_response())

    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.settings.llm_explicit_prompt_cache", True)
    monkeypatch.setattr(executor, "_resolve_chat_provider", lambda tools: (primary, None))
    monkeypatch.setattr(executor, "_messages_for_round", lambda msgs: msgs)
    monkeypatch.setattr(executor, "_remember_dead_provider", lambda **kw: None)
    monkeypatch.setattr(
        executor,
        "_stable_fallback_provider",
        lambda pass_tools, failed_provider=None: fb,
    )
    # effective model = qwen3.7-max → 用**真实注册表** (已 supports_explicit_cache=True) 门控置信号
    executor._last_effective_model_id = "qwen3.7-max"

    with patch.object(fb, "_get_client", return_value=fb_client):
        await executor._call_llm(_MSGS, [])

    _, kwargs = fb_client.chat.completions.create.call_args
    assert kwargs["messages"][0]["content"] == "SYS"          # string content 原样
    assert not isinstance(kwargs["messages"][0]["content"], list)  # 无 cache_control 数组
    assert "prompt_cache_markers" not in kwargs               # 信号未泄漏进 create()
