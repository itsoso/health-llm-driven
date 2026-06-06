# -*- coding: utf-8 -*-
"""数据质量 → Agent 置信度门控(Next Horizon Tier 5)。

Twin 多源、新鲜度参差。Agent 不应对**陈旧/稀疏**数据过度自信。本服务给一个整体
数据置信度,注入 LLM 上下文(twin_to_prompt_blob 顶部),让所有 specialist/orchestrator
在数据差时**多 hedge、少断言、先建议补测**。信任 + 安全的底层改进。

诚实:这是基于"活跃数据源数量"的启发式完整度分,非严格不确定性量化;
只读 twin,不改判定逻辑,只调措辞。
"""
from __future__ import annotations

from typing import Any

# 达到这个活跃数据源数量视为"数据充分"
_TARGET_SOURCES = 5


def assess_data_confidence(twin: Any) -> dict[str, Any]:
    """评估整体数据置信度(去标识,只读 twin.meta.data_sources)。"""
    meta = getattr(twin, "meta", None)
    sources = list(getattr(meta, "data_sources", []) or [])
    n = len(sources)
    score = round(min(1.0, n / _TARGET_SOURCES), 2)
    if score >= 0.67:
        level, hint = "high", ""
    elif score >= 0.34:
        level, hint = "medium", (
            "数据置信度中等:部分来源缺失/陈旧,结论用词适度保守,必要时建议复测。"
        )
    else:
        level, hint = "low", (
            "数据置信度低:多数来源缺失/稀疏,回答多用'可能/建议先补测',"
            "避免确定性断言与具体数值承诺。"
        )
    return {
        "score": score,
        "level": level,
        "present_sources": n,
        "sources": sources,
        "hedge_hint": hint,
    }
