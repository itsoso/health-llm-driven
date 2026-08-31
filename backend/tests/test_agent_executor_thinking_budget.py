"""合成轮思考封顶(SYNTHESIS_THINKING_BUDGET)的门控测试。

不变量(全部 fail-closed):
  - 默认 0 = 关 = 零行为变更(绝不注入 thinking_budget);
  - 只对 ModelEntry.supports_thinking_budget=True 的模型注入(未验证的 qwen 不碰);
  - 本回合调过 health_analysis(深度分析/安全裁决)→ 跳过(保留完整思考);
  - 解析不出 effective model → 跳过;
  - 只在无 tools 的合成/答案轮触发(调用点保证), 绝不碰工具决策轮。
"""
import pytest

from app.config import settings
from app.services.agent_executor import AgentExecutor
from app.services.llm import model_registry as reg


def _executor(model_id, deep_analysis=False, tier=None):
    """构造一个不走 __init__ 的最小实例, 只填门控要读的属性。"""
    obj = AgentExecutor.__new__(AgentExecutor)
    obj._last_effective_model_id = model_id
    obj._turn_invoked_deep_analysis = deep_analysis
    obj._staged_response_mode = "on"
    obj._staged_answer_task_tier = tier
    return obj


# ──── registry / config 静态不变量 ────

def test_only_probed_models_advertise_thinking_budget():
    """fail-closed: 只有真网探针验证过的模型声明 supports_thinking_budget。

    当前白名单: qwen3.7-max (probe 2026-07-12) + qwen3.7-plus (probe 2026-07-13,
    见 6996d1f82)。新模型必须先跑 scripts/probe_qwen_thinking_budget.py 再进这里。
    """
    supported = sorted(m.id for m in reg.MODELS if getattr(m, "supports_thinking_budget", False))
    assert supported == ["qwen3.7-max", "qwen3.7-plus"], (
        f"意外改动了 thinking-budget 白名单: {supported}"
    )


def test_config_default_disabled():
    assert getattr(settings, "synthesis_thinking_budget", 0) == 0


def test_balanced_config_has_a_bounded_default():
    assert getattr(settings, "balanced_synthesis_thinking_budget", 0) == 512


# ──── 门控行为 ────

def test_disabled_by_default_no_injection(monkeypatch):
    monkeypatch.setattr(settings, "synthesis_thinking_budget", 0, raising=False)
    sk = {"messages": []}
    _executor("qwen3.7-max")._maybe_apply_synthesis_thinking_budget(sk)
    assert "thinking_budget" not in sk


def test_injects_when_enabled_and_model_supports(monkeypatch):
    monkeypatch.setattr(settings, "synthesis_thinking_budget", 512, raising=False)
    sk = {"messages": []}
    _executor("qwen3.7-max")._maybe_apply_synthesis_thinking_budget(sk)
    assert sk["thinking_budget"] == 512


def test_balanced_turn_uses_tier_budget_without_enabling_global_budget(monkeypatch):
    monkeypatch.setattr(settings, "synthesis_thinking_budget", 0, raising=False)
    monkeypatch.setattr(
        settings,
        "balanced_synthesis_thinking_budget",
        512,
        raising=False,
    )
    sk = {"messages": []}

    _executor("qwen3.7-plus", tier="balanced")._maybe_apply_synthesis_thinking_budget(sk)

    assert sk["thinking_budget"] == 512


def test_high_stakes_turn_never_inherits_a_thinking_cap(monkeypatch):
    monkeypatch.setattr(settings, "synthesis_thinking_budget", 512, raising=False)
    monkeypatch.setattr(
        settings,
        "balanced_synthesis_thinking_budget",
        512,
        raising=False,
    )
    sk = {"messages": []}

    _executor("qwen3.7-max", tier="high_stakes")._maybe_apply_synthesis_thinking_budget(sk)

    assert "thinking_budget" not in sk


def test_skips_unsupported_model(monkeypatch):
    monkeypatch.setattr(settings, "synthesis_thinking_budget", 512, raising=False)
    sk = {"messages": []}
    # qwen3.6-plus 未跑探针 → supports_thinking_budget=False → 不注入(免端点 400)
    _executor("qwen3.6-plus")._maybe_apply_synthesis_thinking_budget(sk)
    assert "thinking_budget" not in sk


def test_skips_when_deep_analysis_invoked(monkeypatch):
    monkeypatch.setattr(settings, "synthesis_thinking_budget", 512, raising=False)
    sk = {"messages": []}
    # 本回合调过 health_analysis → 保留完整思考, 不封顶
    _executor("qwen3.7-max", deep_analysis=True)._maybe_apply_synthesis_thinking_budget(sk)
    assert "thinking_budget" not in sk


def test_skips_when_no_effective_model(monkeypatch):
    monkeypatch.setattr(settings, "synthesis_thinking_budget", 512, raising=False)
    sk = {"messages": []}
    _executor(None)._maybe_apply_synthesis_thinking_budget(sk)
    assert "thinking_budget" not in sk


def test_skips_unknown_model_id(monkeypatch):
    monkeypatch.setattr(settings, "synthesis_thinking_budget", 512, raising=False)
    sk = {"messages": []}
    _executor("no-such-model")._maybe_apply_synthesis_thinking_budget(sk)
    assert "thinking_budget" not in sk
