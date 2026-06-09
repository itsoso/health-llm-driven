# -*- coding: utf-8 -*-
"""多模型 panel(RFC 方向八)—— 高风险裁决多模型投票,降低单模型幻觉风险。

对高风险问题(safety / 危机 / 临床判断),并行问 N 个模型,聚合投票 + 标注分歧。
单模型可能幻觉/越界;多模型一致才高置信,分歧则升级人工/保守。

安全切入:flag 门控(settings.multi_model_panel,默认关);panel 是 primitive,
真实接入高风险决策点需成本/延迟权衡(每问 ×N 成本)。

诚实:聚合逻辑确定性可测;**真实"多模型能否抓住幻觉"需线上 eval**,不在 CI 验证;
自由文本一致性判断交给调用方抽成标签后再投票(本模块只做标签聚合 + 并行编排)。
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, Optional


def aggregate_votes(labels: list[Optional[str]]) -> dict[str, Any]:
    """对一组(已抽取的)标签做多数投票 + 一致度(纯函数,可测)。

    返回 {decision, agreement(0-1), n, unanimous, counts}。
    全空 → decision=None。归一化:strip+lower。
    """
    norm = [str(x).strip().lower() for x in labels if x is not None and str(x).strip()]
    n = len(norm)
    if n == 0:
        return {"decision": None, "agreement": None, "n": 0, "unanimous": False, "counts": {}}
    counts = Counter(norm)
    decision, top = counts.most_common(1)[0]
    return {
        "decision": decision,
        "agreement": round(top / n, 3),
        "n": n,
        "unanimous": top == n,
        "counts": dict(counts),
    }


def _content(result: Any) -> str:
    if isinstance(result, dict):
        return (result.get("content") or "").strip()
    return str(result or "").strip()


async def run_panel(messages: list[dict], model_ids: list[str], *,
                    temperature: float = 0.0, max_tokens: int = 800) -> dict[str, Any]:
    """并行问多个模型,返回各自回答(供调用方抽标签后 aggregate_votes)。

    某模型失败 → 该条 error,不影响其他(降级不假装)。flag 由调用方在外层判断。
    """
    from app.services.llm.factory import _create_from_entry
    from app.services.llm.model_registry import get_model

    async def _one(mid: str) -> dict[str, Any]:
        try:
            entry = get_model(mid)
            if entry is None:
                return {"model": mid, "error": "unknown_model"}
            provider = _create_from_entry(entry)
            raw = await provider.chat(messages=messages, temperature=temperature, max_tokens=max_tokens)
            return {"model": mid, "text": _content(raw)}
        except Exception as e:  # noqa: BLE001
            return {"model": mid, "error": str(e)[:120]}

    results = await asyncio.gather(*[_one(m) for m in model_ids])
    ok = [r for r in results if "text" in r]
    return {"responses": list(results), "answered": len(ok), "requested": len(model_ids)}
