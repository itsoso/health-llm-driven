# -*- coding: utf-8 -*-
"""F2/F3a/F3b failover 脊柱回归 (2026-07-05 生产事故: langbridge 商用模型工具轮
chat_stream 每轮死等 ~19s, 降级落到 MiniMax 弱工具模型吐 XML 文本工具调用)。

钉四条不变量:
  F2  — 工具轮 provider 失败时, 回退目标必须经**同一可靠工具模型选择逻辑**, 不许
        落到 MiniMax/glm 家族; 非工具轮回退行为不变 (默认 tokenplan)。
  F3a — 同一 run 里 selected provider 首次失败后记住; 后续轮不再重建/重试它 (工具轮
        死只影响工具轮, 无工具合成轮仍可用它)。
  F3b — supports_streaming=False 的模型不走 chat_stream, 改走非流式 chat() 桥, 单块
        产出适配回流式事件; 内容完整。
  flag 缺省 (可流式模型 + 无死亡备忘) 行为零变化。
"""
from unittest.mock import MagicMock

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.llm import model_registry as reg


def _executor():
    ex = AgentExecutor(db=MagicMock())
    ex._current_user_id = None
    ex._request_model_id = None
    ex._prefer_fast_record_model = False
    ex._dead_provider_model_ids = set()
    ex._tool_dead_provider_model_ids = set()
    ex._last_effective_model_id = None
    return ex


async def _drain(agen):
    return [evt async for evt in agen]


# ──────────────────────────── F2: 工具轮回退经可靠工具模型 ────────────────────────────

def test_stable_fallback_for_tools_uses_reliable_model_not_minimax(monkeypatch):
    """带工具回退 → 经 pick_reliable_tool_model_id, 落到可靠模型, 而非默认 tokenplan(MiniMax)。"""
    reliable = MagicMock(name="qwen_reliable")
    reliable.model = "qwen3.7-max"

    def fake_pick(**_k):
        return "qwen3.7-max"

    def fake_create_by_id(mid):
        assert mid == "qwen3.7-max"
        return reliable

    def boom_create_tokenplan(_kind):  # 若走默认 tokenplan 分支就炸 → 证明没走
        raise AssertionError("tool-turn fallback must NOT use default tokenplan (MiniMax)")

    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", fake_pick)
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", fake_create_by_id)
    monkeypatch.setattr(factory, "create_llm_provider", boom_create_tokenplan)

    ex = _executor()
    provider = ex._stable_fallback_provider(pass_tools=True)
    assert provider is reliable
    assert ex._last_provider_model_name == "qwen3.7-max"


def test_stable_fallback_for_tools_excludes_failed_provider(monkeypatch):
    """TokenPlan 额度/故障后必须跨 provider，不能在同一故障域内换模型假降级。"""
    cross_provider = MagicMock(name="langbridge_reliable")
    cross_provider.model = "commercial/GPT-5.5"
    cross_provider.provider_name = "langbridge-proxy"
    failed = MagicMock(name="failed_tokenplan")
    failed.provider_name = "tokenplan"
    picked = {}

    def fake_pick(**kwargs):
        picked.update(kwargs)
        return "gpt-5.5"

    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", fake_pick)
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", lambda mid: cross_provider)

    ex = _executor()
    provider = ex._stable_fallback_provider(
        pass_tools=True,
        failed_provider=failed,
    )

    assert provider is cross_provider
    assert picked["exclude_providers"] == {"tokenplan"}
    assert ex._last_provider_model_name == "commercial/GPT-5.5"


def test_stable_fallback_for_tools_no_reliable_falls_back_to_default(monkeypatch):
    """无可靠模型可用 (env 缺) → 回默认 tokenplan 并 log, 依赖兜底解析 (fail-open)。"""
    default = MagicMock(name="tokenplan_default")
    default.model = "MiniMax-M2.5"

    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **_k: None)
    import app.services.llm.factory as factory
    import app.services.llm.pii_scrub as pii
    import app.services.llm.usage_tracker as tracker
    monkeypatch.setattr(factory, "create_llm_provider", lambda _kind: default)
    monkeypatch.setattr(pii, "wrap_provider_pii_scrub", lambda p: p)
    monkeypatch.setattr(tracker, "wrap_provider", lambda p: p)

    ex = _executor()
    provider = ex._stable_fallback_provider(pass_tools=True)
    assert provider is default  # fail-open: 有回答优先


def test_stable_fallback_non_tool_turn_unchanged(monkeypatch):
    """非工具轮回退 → 默认 tokenplan, 不碰可靠工具模型选择 (行为不变)。"""
    default = MagicMock(name="tokenplan_default")
    default.model = "MiniMax-M2.5"
    pick_called = {"n": 0}

    def spy_pick(**_k):
        pick_called["n"] += 1
        return "qwen3.7-max"

    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", spy_pick)
    import app.services.llm.factory as factory
    import app.services.llm.pii_scrub as pii
    import app.services.llm.usage_tracker as tracker
    monkeypatch.setattr(factory, "create_llm_provider", lambda _kind: default)
    monkeypatch.setattr(pii, "wrap_provider_pii_scrub", lambda p: p)
    monkeypatch.setattr(tracker, "wrap_provider", lambda p: p)

    ex = _executor()
    provider = ex._stable_fallback_provider(pass_tools=False)
    assert provider is default
    assert pick_called["n"] == 0  # 非工具轮不触发可靠模型选择


# ──────────────────────────── F3a: 回合内 provider 死亡备忘 ────────────────────────────

def test_dead_provider_skipped_on_second_tool_round(monkeypatch):
    """selected model 工具轮死后, 第二个工具轮不再工厂重建它, 直接走稳定回退。"""
    created_ids = []

    def fake_create_by_id(mid):
        created_ids.append(mid)
        p = MagicMock(name=f"{mid}_provider")
        p.model = mid
        return p

    reliable = MagicMock(name="reliable_fb")
    reliable.model = "qwen3.7-max"

    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", fake_create_by_id)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **_k: "qwen3.7-max")

    ex = _executor()
    ex._request_model_id = "claude-opus-4.7"

    # 第一个工具轮: 正常解析出 claude provider (工厂建一次)。
    provider1, _ = ex._resolve_chat_provider([{"type": "function"}])
    assert created_ids == ["claude-opus-4.7", "qwen3.7-max"] or created_ids == ["claude-opus-4.7"]
    # 模拟它工具轮失败 → 记死。
    ex._remember_dead_provider(tool_specific=True)
    created_ids.clear()

    # 第二个工具轮: 不再重建 claude, 直接走稳定回退 (qwen)。
    provider2, _ = ex._resolve_chat_provider([{"type": "function"}])
    assert "claude-opus-4.7" not in created_ids, "已死 provider 不应被工厂重建"
    assert provider2 is reliable or getattr(provider2, "model", None) == "qwen3.7-max"
    assert "selected_provider_dead_this_turn" in ex._model_fallback_reasons


def test_tool_dead_does_not_poison_synthesis_round(monkeypatch):
    """仅工具轮死 → 无工具的合成轮仍可用原 selected model (Opus 合成质量不丢)。"""
    created_ids = []

    def fake_create_by_id(mid):
        created_ids.append(mid)
        p = MagicMock(name=f"{mid}_provider")
        p.model = mid
        return p

    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", fake_create_by_id)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **_k: "qwen3.7-max")

    ex = _executor()
    ex._request_model_id = "claude-opus-4.7"
    ex._last_effective_model_id = "claude-opus-4.7"
    ex._remember_dead_provider(tool_specific=True)  # 工具轮死
    created_ids.clear()

    # 合成轮 (无工具): 仍应重建 claude, 不走死亡备忘。
    provider, pass_tools = ex._resolve_chat_provider(None)
    assert created_ids == ["claude-opus-4.7"], "工具轮死不该毒化无工具合成轮"
    assert pass_tools is None


def test_hard_dead_skips_all_rounds(monkeypatch):
    """无工具轮也失败 = 彻底死 → 连合成轮也跳过它。"""
    created_ids = []

    def fake_create_by_id(mid):
        created_ids.append(mid)
        p = MagicMock(name=f"{mid}_provider")
        p.model = mid
        return p

    import app.services.llm.factory as factory
    import app.services.llm.pii_scrub as pii
    import app.services.llm.usage_tracker as tracker
    monkeypatch.setattr(factory, "create_provider_for_model_id", fake_create_by_id)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **_k: None)
    monkeypatch.setattr(factory, "create_llm_provider", lambda _kind: MagicMock(model="MiniMax-M2.5"))
    monkeypatch.setattr(pii, "wrap_provider_pii_scrub", lambda p: p)
    monkeypatch.setattr(tracker, "wrap_provider", lambda p: p)

    ex = _executor()
    ex._request_model_id = "claude-opus-4.7"
    ex._last_effective_model_id = "claude-opus-4.7"
    ex._remember_dead_provider(tool_specific=False)  # 彻底死
    created_ids.clear()

    provider, _ = ex._resolve_chat_provider(None)  # 合成轮
    assert "claude-opus-4.7" not in created_ids, "彻底死的 provider 连合成轮也不该重建"


# ──────────────────────────── F3b: 非流式桥 ────────────────────────────

def test_non_streaming_model_flag_from_registry():
    """langbridge 三条商用 entry supports_streaming=False; tokenplan 流式模型 True。"""
    for mid in ("claude-opus-4.7", "gpt-5.5", "gemini-3.1-pro"):
        assert reg.get_model(mid).supports_streaming is False
    for mid in ("qwen3.7-plus", "qwen3.7-max", "deepseek-v4-flash"):
        assert reg.get_model(mid).supports_streaming is True


@pytest.mark.asyncio
async def test_non_streaming_bridge_uses_chat_not_stream(monkeypatch):
    """supports_streaming=False → _call_llm_stream 走 chat() 桥, 单块产出完整内容,
    绝不调 chat_stream。"""
    class FakeOpus:
        model = "commercial/Claude-Opus-4.7"

        async def chat(self, **kwargs):
            assert kwargs.get("stream") is False
            return {"content": "完整的一段答案。", "finish_reason": "stop"}

        async def chat_stream(self, **kwargs):
            raise AssertionError("non-streaming model must not go through chat_stream")
            yield  # pragma: no cover

    ex = _executor()
    ex._request_model_id = "claude-opus-4.7"
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda mid: FakeOpus(),
    )
    # 无 AGENT_BASE_URL 直连分支
    from app.services.agent_executor import settings as ax_settings
    monkeypatch.setattr(ax_settings, "agent_base_url", None, raising=False)
    monkeypatch.setattr(ax_settings, "agent_api_key", None, raising=False)

    events = await _drain(ex._call_llm_stream([{"role": "user", "content": "hi"}], []))
    content = "".join(e.get("text", "") for e in events if e.get("type") == "content")
    assert content == "完整的一段答案。"
    finishes = [e for e in events if e.get("type") == "finish"]
    assert finishes and finishes[-1]["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_streaming_model_still_streams(monkeypatch):
    """flag 缺省 (可流式模型) → 仍走 chat_stream 真流式, 行为零变化。"""
    stream_called = {"n": 0}

    class FakeQwen:
        model = "qwen3.7-max"

        async def chat(self, **kwargs):
            raise AssertionError("streaming model must not use non-stream bridge")

        async def chat_stream(self, **kwargs):
            stream_called["n"] += 1
            yield {"type": "content", "text": "流式 "}
            yield {"type": "content", "text": "分片"}
            yield {"type": "finish", "finish_reason": "stop"}

    ex = _executor()
    ex._request_model_id = "qwen3.7-max"
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda mid: FakeQwen(),
    )
    from app.services.agent_executor import settings as ax_settings
    monkeypatch.setattr(ax_settings, "agent_base_url", None, raising=False)
    monkeypatch.setattr(ax_settings, "agent_api_key", None, raising=False)

    events = await _drain(ex._call_llm_stream([{"role": "user", "content": "hi"}], []))
    content = "".join(e.get("text", "") for e in events if e.get("type") == "content")
    assert content == "流式 分片"
    assert stream_called["n"] == 1
