# -*- coding: utf-8 -*-
"""任务分级 → 模型路由(成本/延迟,Next Horizon Tier 4 / RFC 方向十)。

高风险裁决(safety/longevity/clinical)用强模型;日常/闲聊用快且便宜的模型。
复用 model_registry 已有的 speed_tier(fast/balanced/reasoning),不重复定义模型。

安全切入:flag 门控(settings.task_tiered_routing,默认关)+ create_provider_for_user
加可选 task_tier(默认 None)。flag 关 或 不传 tier → **零行为变更**。
"""
from __future__ import annotations

from typing import Optional

from app.services.llm.model_registry import list_models

# 任务档 → 期望 speed_tier
_TASK_TIER_TO_SPEED = {
    "high_stakes": "reasoning",   # safety / 抗衰裁决 / 临床
    "balanced": "balanced",       # 综合分析
    "casual": "fast",             # 闲聊 / 轻量
}

# 目标 speed_tier 无可用模型时的回退顺序 —— 对注册表裁剪鲁棒(如套餐收敛后不再有 fast 档,
# casual 自动落到 balanced,而不是返回 None 让任务路由整个失效)。
_SPEED_FALLBACK = {
    "fast": ("fast", "balanced", "reasoning"),
    "balanced": ("balanced", "reasoning", "fast"),
    "reasoning": ("reasoning", "balanced", "fast"),
}


def pick_model_id_by_tier(task_tier: Optional[str], only_available: bool = True) -> Optional[str]:
    """按任务档选一个对应 speed_tier 的可用模型 id;目标档无模型时按 _SPEED_FALLBACK 降级;
    全无 → None(调用方回退默认)。"""
    speed = _TASK_TIER_TO_SPEED.get((task_tier or "").lower())
    if speed is None:
        return None
    models = list_models(only_available=only_available)
    for target in _SPEED_FALLBACK.get(speed, (speed,)):
        for m in models:
            if getattr(m, "speed_tier", None) == target:
                return m.id
    return None
