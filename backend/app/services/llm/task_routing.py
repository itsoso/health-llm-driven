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
    # 内部工具决策轮 (agent tool-decision round): 只产出结构化 function call,
    # 无任何面向用户的医疗正文。这是**唯一**被显式授权降到 fast 的档 (见下方白名单)。
    # 合成/答案轮不走这个档 —— 它们无 tools, 由质量模型生成医疗结论。
    "tool_routing": "fast",
}

# ── 安全不变量(fail-closed):哪些任务档允许真的落到 fast(弱)模型 ──
# 只有**明确无医疗内容生成**的档才准降到 fast:简单查数 / 记录写入的意图分类 /
# 内部辅助任务。任何面向用户的医疗内容生成(健康建议 / 安全评估 / orchestrator
# 合成 / 专科叙事)绝不允许降到 fast —— 弱模型编造/漏说医疗结论是不可接受的风险。
#
# 强制点在 pick_model_id_by_tier:tier 不在此白名单时,即便目标/回退档命中 fast 模型
# 也会被地板到 non-fast(balanced)。将来若真有"记录写入意图分类"这类纯内部快任务,
# 显式往这里加档名并配对抗测试,别偷偷放宽。
#
# 2026-07-06:加入 "tool_routing" —— agent 工具决策轮 (tool-decision round)。
# 该档**只**代表"模型输出一个结构化 function call"这一步 (agent_executor 的带 tools 轮),
# 绝无面向用户的医疗正文:安全评估是确定性 SafetyGuardian、写入受 R4 draft/confirm 门控,
# 都与这一步用哪个模型无关。合成/答案轮 (无 tools) 恒不走此档,仍由质量模型生成医疗结论。
# 说明:此白名单只声明"该内部档**允许**降到 fast";落到具体模型时,tool 轮必须是
# reliable_tool_calling=True 的 fast 模型 (由 agent_executor 经 pick_reliable_tool_model_id
# 选,而非本文件的 pick_model_id_by_tier —— 后者不保证工具可靠性)。见 test_task_routing*。
_FAST_ELIGIBLE_TIERS: frozenset[str] = frozenset({"tool_routing"})

# 目标 speed_tier 无可用模型时的回退顺序 —— 对注册表裁剪鲁棒(如套餐收敛后不再有 fast 档,
# casual 自动落到 balanced,而不是返回 None 让任务路由整个失效)。
_SPEED_FALLBACK = {
    "fast": ("fast", "balanced", "reasoning"),
    "balanced": ("balanced", "reasoning", "fast"),
    "reasoning": ("reasoning", "balanced", "fast"),
}


def pick_model_id_by_tier(task_tier: Optional[str], only_available: bool = True) -> Optional[str]:
    """按任务档选一个对应 speed_tier 的可用模型 id;目标档无模型时按 _SPEED_FALLBACK 降级;
    全无 → None(调用方回退默认)。

    安全不变量(fail-closed):tier 不在 _FAST_ELIGIBLE_TIERS 时,绝不返回 fast 档模型 ——
    fast 目标 / fast 回退项一律被跳过并地板到 non-fast。未知 tier → None(默认模型)。
    """
    tier_key = (task_tier or "").lower()
    speed = _TASK_TIER_TO_SPEED.get(tier_key)
    if speed is None:
        return None
    fast_allowed = tier_key in _FAST_ELIGIBLE_TIERS
    models = list_models(only_available=only_available)
    for target in _SPEED_FALLBACK.get(speed, (speed,)):
        if target == "fast" and not fast_allowed:
            # fail-closed:非白名单档不许落到弱模型,跳过 fast 继续找 balanced/reasoning。
            continue
        for m in models:
            if getattr(m, "speed_tier", None) == target:
                return m.id
    return None
