# -*- coding: utf-8 -*-
"""任务分级模型路由(Next Horizon Tier 4 / RFC 方向十)回归。

钉:tier→speed_tier 选模型;flag 关=零行为变更(不走路由);flag 开+匹配=用 tier 模型。
"""
from unittest.mock import MagicMock, patch


def test_pick_model_id_by_tier():
    from app.services.llm.task_routing import pick_model_id_by_tier
    # only_available=False:不依赖 env,只验"按 speed_tier 选到对应档模型"
    hs = pick_model_id_by_tier("high_stakes", only_available=False)
    casual = pick_model_id_by_tier("casual", only_available=False)
    bal = pick_model_id_by_tier("balanced", only_available=False)
    assert hs and casual and bal
    from app.services.llm.model_registry import get_model
    assert get_model(hs).speed_tier == "reasoning"
    # casual 期望 fast;套餐收敛后注册表无 fast 档 → 按 _SPEED_FALLBACK 降级(balanced/reasoning)
    assert get_model(casual).speed_tier in ("fast", "balanced", "reasoning")
    assert get_model(bal).speed_tier == "balanced"
    assert pick_model_id_by_tier("nonsense", only_available=False) is None
    assert pick_model_id_by_tier(None) is None


def test_tier_for_intent_wiring():
    """成本路由接线:orchestrator 按 intent 类别定 task_tier(高风险→reasoning)。"""
    from app.orchestrator.orchestrator import _tier_for_intent

    class _I:
        def __init__(self, c): self.categories = c
    assert _tier_for_intent(_I(["safety"])) == "high_stakes"
    assert _tier_for_intent(_I(["longevity"])) == "high_stakes"
    assert _tier_for_intent(_I(["recovery"])) == "balanced"
    assert _tier_for_intent(_I(["fuel", "movement"])) == "balanced"
    assert _tier_for_intent(_I(["general"])) == "casual"
    assert _tier_for_intent(_I([])) == "casual"


def test_routing_taken_when_flag_on():
    """flag 开 + tier 匹配 → 用 tier 模型(不落到用户偏好/默认)。"""
    from app.config import settings
    from app.services.llm import factory

    sentinel = object()
    with patch.object(settings, "task_tiered_routing", True), \
         patch("app.services.llm.task_routing.pick_model_id_by_tier", return_value="m-x"), \
         patch("app.services.llm.model_registry.get_model", return_value=MagicMock()), \
         patch.object(factory, "_create_from_entry", return_value="raw"), \
         patch("app.services.llm.usage_tracker.wrap_provider", side_effect=lambda x: x), \
         patch("app.services.llm.pii_scrub.wrap_provider_pii_scrub", return_value=sentinel):
        out = factory.create_provider_for_user(1, MagicMock(), task_tier="high_stakes")
    assert out is sentinel


def test_routing_skipped_when_flag_off():
    """flag 关 → 不走路由(zero behavior change),回退既有逻辑。"""
    from app.config import settings
    from app.services.llm import factory

    pick = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # 无 user 偏好
    with patch.object(settings, "task_tiered_routing", False), \
         patch("app.services.llm.task_routing.pick_model_id_by_tier", pick), \
         patch.object(factory, "get_llm_provider", return_value="default-provider"):
        out = factory.create_provider_for_user(1, db, task_tier="high_stakes")
    pick.assert_not_called()        # flag 关 → 根本不调用路由
    assert out == "default-provider"
