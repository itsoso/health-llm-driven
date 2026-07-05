# -*- coding: utf-8 -*-
"""分层任务路由「通电」确定性 eval —— 供主 session 放心把 TASK_TIERED_ROUTING=true
写进生产 .env 前锁死行为。

覆盖:
  (a) 各类样例任务在 flag=true 下路由到预期档;
  (b) 健康建议 / 安全 / 合成类样例恒不降到 fast(弱模型)—— 安全不变量 fail-closed;
  (c) 目标档无可用模型时回退默认,无 crash、无静默弱模型;
  (d) flag=false 时行为与现状完全一致(回归保护)。

只依赖注册表 + 纯函数,不打真实 LLM。
"""
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm import task_routing
from app.services.llm.task_routing import pick_model_id_by_tier
from app.services.llm.model_registry import get_model, list_models
from app.orchestrator.orchestrator import _tier_for_intent


# ── 测试用最小 ModelEntry 替身(只需 id + speed_tier) ──
@dataclass(frozen=True)
class _FakeModel:
    id: str
    speed_tier: str


class _Intent:
    def __init__(self, categories):
        self.categories = categories


# ─────────────────────────────────────────────────────────────
# (a) intent → tier 分类正确
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("categories,expected_tier", [
    (["safety"], "high_stakes"),
    (["labs"], "high_stakes"),
    (["chronic"], "high_stakes"),
    (["mental"], "high_stakes"),
    (["longevity"], "high_stakes"),
    (["safety", "general"], "high_stakes"),   # 高风险与 general 混合 → 仍高风险
    (["recovery"], "balanced"),
    (["fuel"], "balanced"),
    (["movement"], "balanced"),
    (["fuel", "movement"], "balanced"),
    (["general"], "balanced"),                # 合成是医疗内容 → 地板 balanced,不降 casual
    ([], "balanced"),                         # 空 categories → balanced
])
def test_intent_maps_to_expected_tier(categories, expected_tier):
    assert _tier_for_intent(_Intent(categories)) == expected_tier


# ─────────────────────────────────────────────────────────────
# (a) tier → 目标 speed_tier 的真实模型
# ─────────────────────────────────────────────────────────────

def test_high_stakes_routes_to_reasoning():
    mid = pick_model_id_by_tier("high_stakes", only_available=False)
    assert mid is not None
    assert get_model(mid).speed_tier == "reasoning"


def test_balanced_routes_to_balanced():
    mid = pick_model_id_by_tier("balanced", only_available=False)
    assert mid is not None
    assert get_model(mid).speed_tier == "balanced"


def test_unknown_tier_returns_none():
    # 未知档 → None(调用方回退默认),绝不猜。
    assert pick_model_id_by_tier("nonsense", only_available=False) is None
    assert pick_model_id_by_tier(None, only_available=False) is None
    assert pick_model_id_by_tier("", only_available=False) is None


# ─────────────────────────────────────────────────────────────
# (b) 安全不变量:任何 tier 都不许落到 fast(弱)模型 —— fail-closed
# ─────────────────────────────────────────────────────────────

def test_no_tier_ever_routes_to_fast_model_in_real_registry():
    """真实注册表下,三档全跑一遍,选中的模型都不能是 fast 档。
    (当前 _FAST_ELIGIBLE_TIERS 为空 → fast 对所有档都不可达。)"""
    for tier in ("high_stakes", "balanced", "casual"):
        mid = pick_model_id_by_tier(tier, only_available=False)
        if mid is not None:
            assert get_model(mid).speed_tier != "fast", (
                f"tier={tier} 竟路由到 fast 模型 {mid},违反安全不变量"
            )


def test_casual_floored_off_fast_even_when_fast_model_exists():
    """即便注册表里明明有 fast 模型,casual(非 fast-eligible)也必须地板到 balanced。"""
    fake = [
        _FakeModel("flash-x", "fast"),
        _FakeModel("bal-x", "balanced"),
        _FakeModel("reason-x", "reasoning"),
    ]
    with patch.object(task_routing, "list_models", return_value=fake):
        mid = pick_model_id_by_tier("casual", only_available=False)
    assert mid == "bal-x", f"casual 应地板到 balanced,实际 {mid}"


def test_casual_never_fast_even_if_only_fast_and_reasoning_exist():
    """极端:注册表只有 fast + reasoning。casual 不许落 fast → 必须落 reasoning。"""
    fake = [
        _FakeModel("flash-x", "fast"),
        _FakeModel("reason-x", "reasoning"),
    ]
    with patch.object(task_routing, "list_models", return_value=fake):
        mid = pick_model_id_by_tier("casual", only_available=False)
    assert mid == "reason-x", f"casual 宁可 reasoning 也不许 fast,实际 {mid}"


def test_fast_eligible_allowlist_is_empty_by_default():
    """通电前置断言:当前没有任何档被授权降到 fast。
    有人往白名单加档时这条会红,逼其显式确认 + 配对抗测试。"""
    assert task_routing._FAST_ELIGIBLE_TIERS == frozenset()


# ─────────────────────────────────────────────────────────────
# (c) 目标档无模型 → 回退默认,无 crash,无静默弱模型
# ─────────────────────────────────────────────────────────────

def test_balanced_falls_back_when_no_balanced_model():
    """注册表被裁剪到只剩 reasoning:balanced 按 _SPEED_FALLBACK 落到 reasoning,
    不返回 None、不 crash、绝不落 fast。"""
    fake = [_FakeModel("reason-x", "reasoning")]
    with patch.object(task_routing, "list_models", return_value=fake):
        mid = pick_model_id_by_tier("balanced", only_available=False)
    assert mid == "reason-x"


def test_returns_none_when_registry_empty():
    """注册表全空 → None(调用方回退默认),不 crash。"""
    with patch.object(task_routing, "list_models", return_value=[]):
        assert pick_model_id_by_tier("high_stakes", only_available=False) is None
        assert pick_model_id_by_tier("balanced", only_available=False) is None
        assert pick_model_id_by_tier("casual", only_available=False) is None


def test_factory_falls_through_to_default_when_no_tier_model():
    """flag=true 但 pick 返回 None(目标档无模型)→ factory 不能 crash,
    落到既有逻辑(无 user 偏好 → 全局默认),绝不静默用弱模型。"""
    from app.config import settings
    from app.services.llm import factory

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # 无 user 偏好
    with patch.object(settings, "task_tiered_routing", True), \
         patch("app.services.llm.task_routing.pick_model_id_by_tier", return_value=None), \
         patch.object(factory, "get_llm_provider", return_value="default-provider"):
        out = factory.create_provider_for_user(1, db, task_tier="high_stakes")
    assert out == "default-provider"


def test_factory_swallows_routing_error_and_falls_through():
    """路由内部抛异常 → factory 捕获后回退既有逻辑(不 fail-open 到崩,也不静默弱模型)。"""
    from app.config import settings
    from app.services.llm import factory

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(settings, "task_tiered_routing", True), \
         patch("app.services.llm.task_routing.pick_model_id_by_tier",
               side_effect=RuntimeError("boom")), \
         patch.object(factory, "get_llm_provider", return_value="default-provider"):
        out = factory.create_provider_for_user(1, db, task_tier="high_stakes")
    assert out == "default-provider"


# ─────────────────────────────────────────────────────────────
# (d) flag=false → 与现状完全一致(回归保护)
# ─────────────────────────────────────────────────────────────

def test_flag_off_never_invokes_routing():
    """flag 关:pick 根本不被调用,直接回退既有(user 偏好 → 全局默认)。"""
    from app.config import settings
    from app.services.llm import factory

    pick = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(settings, "task_tiered_routing", False), \
         patch("app.services.llm.task_routing.pick_model_id_by_tier", pick), \
         patch.object(factory, "get_llm_provider", return_value="default-provider"):
        out = factory.create_provider_for_user(1, db, task_tier="high_stakes")
    pick.assert_not_called()
    assert out == "default-provider"


def test_flag_off_ignores_tier_for_every_intent_class():
    """flag 关:无论 intent 落哪个档,都不走路由(零行为变更)。"""
    from app.config import settings
    from app.services.llm import factory

    for tier in ("high_stakes", "balanced", "casual"):
        pick = MagicMock()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with patch.object(settings, "task_tiered_routing", False), \
             patch("app.services.llm.task_routing.pick_model_id_by_tier", pick), \
             patch.object(factory, "get_llm_provider", return_value="default-provider"):
            out = factory.create_provider_for_user(1, db, task_tier=tier)
        pick.assert_not_called()
        assert out == "default-provider"


def test_flag_on_high_stakes_uses_tier_model():
    """flag 开 + tier 匹配 → 用 tier 选的模型,不落到用户偏好/默认(接线活着)。"""
    from app.config import settings
    from app.services.llm import factory

    sentinel = object()
    with patch.object(settings, "task_tiered_routing", True), \
         patch("app.services.llm.task_routing.pick_model_id_by_tier", return_value="qwen3.7-max"), \
         patch.object(factory, "_create_from_entry", return_value="raw"), \
         patch("app.services.llm.usage_tracker.wrap_provider", side_effect=lambda x: x), \
         patch("app.services.llm.pii_scrub.wrap_provider_pii_scrub", return_value=sentinel):
        out = factory.create_provider_for_user(1, MagicMock(), task_tier="high_stakes")
    assert out is sentinel
