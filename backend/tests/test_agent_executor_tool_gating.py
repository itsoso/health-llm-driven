"""工具调用能力门控 (model_registry.reliable_tool_calling + agent_executor 选模型层)。

从源头减少弱模型 (glm-5.1 等) 吐坏工具调用: 需要工具的回合若选中不可靠模型,
门控到可靠模型; #147/#161 的兜底解析仍是安全网, 这里不碰。
"""
from unittest.mock import MagicMock

import app.services.agent_executor as ae
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
        lambda only_available=False: [
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
        lambda only_available=False: [
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
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "claude-opus-4.7")

    ex = _executor()
    ex._request_model_id = "glm-5.1"

    provider, pass_tools = ex._resolve_chat_provider([{"type": "function"}])
    assert provider is sentinel_reliable
    assert pass_tools  # tools 仍然下发


def test_gate_keeps_reliable_request_model(monkeypatch):
    """request_model = claude (可靠) → provider 不变。"""
    sentinel = MagicMock(name="claude_provider")
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", lambda mid: sentinel)

    ex = _executor()
    ex._request_model_id = "claude-opus-4.7"

    provider, pass_tools = ex._resolve_chat_provider([{"type": "function"}])
    assert provider is sentinel


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


def test_gate_fast_record_unreliable_redirected(monkeypatch):
    """fast-record 路由到 glm-5.1 (FAST_RECORD_MODEL_ID) + 工具 → 门控到可靠模型。

    这正是 #147/#161 的源头: 记录回合用 glm-5.1 抽参数。
    """
    sentinel_unreliable = MagicMock(name="glm_provider")
    sentinel_reliable = MagicMock(name="claude_provider")

    def fake_create(model_id):
        return sentinel_unreliable if model_id == ae.FAST_RECORD_MODEL_ID else sentinel_reliable

    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", fake_create)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "claude-opus-4.7")

    ex = _executor()
    ex._prefer_fast_record_model = True

    provider, pass_tools = ex._resolve_chat_provider([{"type": "function"}])
    assert provider is sentinel_reliable
    assert pass_tools
