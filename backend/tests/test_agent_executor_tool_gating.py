"""工具调用能力门控 (model_registry.reliable_tool_calling + agent_executor 选模型层)。

从源头减少弱模型 (glm-5.1 等) 吐坏工具调用: 需要工具的回合若选中不可靠模型,
门控到可靠模型; #147/#161 的兜底解析仍是安全网, 这里不碰。
"""
import json
from unittest.mock import MagicMock

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.llm import model_registry as reg


# ──── registry 标注 ────

def test_glm_and_minimax_flagged_unreliable():
    assert reg.get_model("glm-5.1").reliable_tool_calling is False
    assert reg.get_model("minimax-m2.5").reliable_tool_calling is False


def test_langbridge_commercial_models_reliable():
    for mid in ("claude-opus-4.7", "gpt-5.5", "gemini-3.1-pro"):
        assert reg.get_model(mid).reliable_tool_calling is True


def test_is_reliable_unknown_id_defaults_true():
    # 未注册 id 保守 True = 不门控
    assert reg.is_reliable_tool_caller("does-not-exist") is True
    assert reg.is_reliable_tool_caller(None) is True


def test_pick_reliable_prefers_speed_tier(monkeypatch):
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False, include_non_chat=False: [
            reg.ModelEntry("fastrel", "f", "x", "m", "fast", reliable_tool_calling=True),
            reg.ModelEntry("balrel", "b", "x", "m", "balanced", reliable_tool_calling=True),
            reg.ModelEntry("badmodel", "bad", "x", "m", "balanced", reliable_tool_calling=False),
        ],
    )
    # near balanced → 选 balanced 的可靠模型, 跳过不可靠的
    assert reg.pick_reliable_tool_model_id(near_speed_tier="balanced") == "balrel"


def test_pick_reliable_none_when_no_reliable(monkeypatch):
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False, include_non_chat=False: [
            reg.ModelEntry("bad", "bad", "x", "m", "balanced", reliable_tool_calling=False),
        ],
    )
    assert reg.pick_reliable_tool_model_id(near_speed_tier="balanced") is None


# ──── agent_executor 门控逻辑 ────

def _executor():
    ex = AgentExecutor(db=MagicMock())
    ex._current_user_id = None
    ex._request_model_id = None
    ex._prefer_fast_record_model = False
    return ex


def test_gate_redirects_unreliable_request_model_when_tools(monkeypatch):
    """request_model = glm-5.1 (不可靠) + 传 tools → 换可靠模型。"""
    sentinel_unreliable = MagicMock(name="glm_provider")
    sentinel_reliable = MagicMock(name="claude_provider")

    def fake_create(model_id):
        return sentinel_unreliable if model_id == "glm-5.1" else sentinel_reliable

    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", fake_create)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.7-max")

    ex = _executor()
    ex._request_model_id = "glm-5.1"

    provider, pass_tools = ex._resolve_chat_provider([{"type": "function"}])
    assert provider is sentinel_reliable
    assert pass_tools  # tools 仍然下发
    # Subsequent forced-tool policy must describe the provider that will
    # actually receive the request, not the unreliable model it replaced.
    assert ex._last_effective_model_id == "qwen3.7-max"


def test_gate_keeps_reliable_request_model(monkeypatch):
    """request_model = claude (可靠) → provider 不变。"""
    sentinel = MagicMock(name="claude_provider")
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", lambda mid: sentinel)

    ex = _executor()
    ex._request_model_id = "claude-opus-4.7"

    provider, pass_tools = ex._resolve_chat_provider([{"type": "function"}])
    assert provider is sentinel


@pytest.mark.asyncio
async def test_explicit_aigc_turn_forces_draft_on_the_reliable_fallback_model(monkeypatch):
    """AIGC creation must survive an unreliable user-selected chat model."""
    captured = {}

    class ReliableProvider:
        model = "qwen3.7-max"

        async def chat_stream(self, **kwargs):
            captured.update(kwargs)
            yield {"type": "finish", "finish_reason": "stop"}

    import app.services.llm.factory as factory

    monkeypatch.setattr(
        factory,
        "create_provider_for_model_id",
        lambda model_id: ReliableProvider() if model_id == "qwen3.7-max" else MagicMock(),
    )
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **_kwargs: "qwen3.7-max")
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", False)

    ex = _executor()
    ex._request_model_id = "glm-5.1"
    ex._current_turn_user_message = "基于这张照片生成今天活动的短视频，以此照片为开头。"
    tools = [{"type": "function", "function": {"name": "draft_aigc_media"}}]

    _events = [event async for event in ex._call_llm_stream([{"role": "user", "content": "创作"}], tools)]

    assert captured["tool_choice"] == {
        "type": "function",
        "function": {"name": "draft_aigc_media"},
    }
    assert captured["enable_thinking"] is False


def test_gate_skips_when_no_tools(monkeypatch):
    """不传 tools → 即便选中不可靠模型也不门控 (纯文本回合)。"""
    sentinel_unreliable = MagicMock(name="glm_provider")
    import app.services.llm.factory as factory
    monkeypatch.setattr(
        factory, "create_provider_for_model_id",
        lambda mid: sentinel_unreliable,
    )
    called = {"n": 0}
    orig = reg.pick_reliable_tool_model_id

    def spy(**k):
        called["n"] += 1
        return orig(**k)

    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", spy)

    ex = _executor()
    ex._request_model_id = "glm-5.1"

    provider, pass_tools = ex._resolve_chat_provider(None)
    assert provider is sentinel_unreliable
    assert pass_tools is None
    assert called["n"] == 0  # 没传 tools, 门控根本没触发


def test_gate_keeps_unreliable_when_no_reliable_fallback(monkeypatch):
    """需要工具 + 不可靠模型 + 无可回退可靠模型 → 维持现状 (依赖兜底解析)。"""
    sentinel_unreliable = MagicMock(name="glm_provider")
    import app.services.llm.factory as factory
    monkeypatch.setattr(
        factory, "create_provider_for_model_id",
        lambda mid: sentinel_unreliable,
    )
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: None)

    ex = _executor()
    ex._request_model_id = "glm-5.1"

    provider, pass_tools = ex._resolve_chat_provider([{"type": "function"}])
    assert provider is sentinel_unreliable  # 没崩, 不换
    assert pass_tools


def test_fast_record_uses_default_provider_instead_of_hidden_glm(monkeypatch):
    """fast-record only compacts prompts; it must not silently switch to GLM-5.1."""
    sentinel_default = MagicMock(name="default_provider")
    created_model_ids = []

    def fake_create(model_id):
        created_model_ids.append(model_id)
        return MagicMock(name=f"{model_id}_provider")

    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", fake_create)
    monkeypatch.setattr(factory, "get_llm_provider", lambda: sentinel_default)
    monkeypatch.setattr(reg, "get_active_model_id", lambda: None)

    ex = _executor()
    ex._prefer_fast_record_model = True

    provider, pass_tools = ex._resolve_chat_provider([{"type": "function"}])
    assert provider is sentinel_default
    assert created_model_ids == []
    assert pass_tools


@pytest.mark.asyncio
async def test_unreliable_manual_model_uses_fallback_for_tools_then_selected_model_for_final(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    """Manual GLM can borrow Qwen for tool calls, but final synthesis must stay GLM."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls = []
    qwen_stream_calls = {"n": 0}

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):
            provider_calls.append({
                "model": self.model,
                "has_tools": bool(kwargs.get("tools")),
            })
            if self.model == "qwen3.7-max":
                qwen_stream_calls["n"] += 1
                if qwen_stream_calls["n"] == 1:
                    yield {
                        "type": "tool_calls",
                        "tool_calls": [{
                            "id": "env-1",
                            "type": "function",
                            "function": {
                                "name": "environment_check",
                                "arguments": json.dumps({"location": "北京"}),
                            },
                        }],
                    }
                    yield {"type": "finish", "finish_reason": "tool_calls"}
                    return
                yield {"type": "content", "text": "QWEN FINAL"}
                yield {"type": "finish", "finish_reason": "stop"}
                return

            assert self.model == "glm-5.2"
            assert not kwargs.get("tools")
            yield {"type": "content", "text": "GLM FINAL"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(name, args, token):
        assert name == "environment_check"
        return "北京当前 19C 小雨，湿度 92%"

    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda: [{
            "type": "function",
            "function": {
                "name": "environment_check",
                "description": "Check local environment",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda model_id: FakeProvider(model_id),
    )
    monkeypatch.setattr(
        reg,
        "pick_reliable_tool_model_id",
        lambda **_kwargs: "qwen3.7-max",
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="来北京之后有点头疼，怎么办？",
            user_auth_token="test-token",
            extra_context=json.dumps({"client": "mac", "model_id": "glm-5.2"}),
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = events[-1]["data"]

    assert provider_calls == [
        {"model": "qwen3.7-max", "has_tools": True},
        {"model": "glm-5.2", "has_tools": False},
    ]
    assert rendered == "GLM FINAL"
    assert done["model"] == "glm-5.2"
    assert done["selected_model"] == "glm-5.2"
    assert done["answer_model"] == "glm-5.2"
    assert done["tool_models"] == ["qwen3.7-max"]
    assert done["fallback_reasons"] == ["selected_model_tool_unreliable"]
    assert done["tools_used"] == ["environment_check"]


@pytest.mark.asyncio
async def test_provider_error_fallback_for_tools_returns_to_manual_model_for_final(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    """F3b 非流式桥 + F2: Opus(结构性非流式) 走非流式 chat() 桥; 工具轮网关拒绝非流式
    tool-calling → F2 回退到可靠工具模型(测试环境无可靠模型可用 → 默认 tokenplan
    mock=Qwen)拿数据; 最终合成轮仍回 Opus 非流式桥。绝不走 chat_stream 白等超时。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls = []
    qwen_stream_calls = {"n": 0}

    class FakeClaudeProvider:
        # Opus 结构性非流式 → agent 走 chat() 非流式桥, 不调 chat_stream。
        model = "commercial/Claude-Opus-4.7"

        async def chat(self, **kwargs):
            provider_calls.append({
                "model": self.model,
                "has_tools": bool(kwargs.get("tools")),
            })
            if kwargs.get("tools"):
                # 网关浏览器适配器不实现非流式 tool-calling → 500 (生产实况)。
                raise RuntimeError(
                    "Error code: 500 - adapter has no chat() method: TokenPlanAdapter"
                )
            return {"content": "CLAUDE FINAL", "finish_reason": "stop"}

        async def chat_stream(self, **kwargs):
            # 非流式模型不应被调 chat_stream — 命中即测试失败。
            raise AssertionError("non-streaming model must not be called via chat_stream")
            yield  # pragma: no cover — make this an async generator

    class FakeQwenProvider:
        model = "qwen3.7-max"

        async def chat_stream(self, **kwargs):
            provider_calls.append({
                "model": self.model,
                "has_tools": bool(kwargs.get("tools")),
            })
            qwen_stream_calls["n"] += 1
            if qwen_stream_calls["n"] == 1:
                yield {
                    "type": "tool_calls",
                    "tool_calls": [{
                        "id": "env-1",
                        "type": "function",
                        "function": {
                            "name": "environment_check",
                            "arguments": json.dumps({"location": "北京"}),
                        },
                    }],
                }
                yield {"type": "finish", "finish_reason": "tool_calls"}
                return
            yield {"type": "content", "text": "QWEN FINAL"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def fake_execute_tool(name, args, token):
        assert name == "environment_check"
        return "北京当前 19C 小雨，湿度 92%"

    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda: [{
            "type": "function",
            "function": {
                "name": "environment_check",
                "description": "Check local environment",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda model_id: FakeClaudeProvider() if model_id == "claude-opus-4.7" else FakeQwenProvider(),
    )
    monkeypatch.setattr("app.services.llm.factory.create_llm_provider", lambda _kind: FakeQwenProvider())
    monkeypatch.setattr("app.services.llm.pii_scrub.wrap_provider_pii_scrub", lambda p: p)
    monkeypatch.setattr("app.services.llm.usage_tracker.wrap_provider", lambda p: p)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="来北京之后有点头疼，怎么办？",
            user_auth_token="test-token",
            extra_context=json.dumps({"client": "mac", "model_id": "claude-opus-4.7"}),
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = events[-1]["data"]

    # 工具轮: Opus 非流式桥 chat(tools) → 网关拒绝 → F2 回退到 Qwen (可靠工具模型)。
    # 合成轮: Opus 非流式桥 chat(no-tools) → 成功产出最终答案。绝无 Opus chat_stream。
    assert provider_calls == [
        {"model": "commercial/Claude-Opus-4.7", "has_tools": True},
        {"model": "qwen3.7-max", "has_tools": True},
        {"model": "commercial/Claude-Opus-4.7", "has_tools": False},
    ]
    assert rendered == "CLAUDE FINAL"
    assert done["model"] == "commercial/Claude-Opus-4.7"
    assert done["selected_model"] == "commercial/Claude-Opus-4.7"
    assert done["answer_model"] == "commercial/Claude-Opus-4.7"
    assert done["tool_models"] == ["qwen3.7-max"]
    assert done["fallback_reasons"] == ["selected_model_tool_bridge_failed"]
    assert done["tools_used"] == ["environment_check"]
