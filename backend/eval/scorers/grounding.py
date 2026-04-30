"""Grounding scorer — 验证 LLM 输出的 evidence_refs 是否真的来自给定输入.

适用: Insight Pattern Mining 这类要求 LLM 引用具体数据的场景, 防幻觉.

核心检查:
1. 每条 evidence_ref 是否存在于 available pool
2. 有效 ref 数量 >= min_valid_refs
3. confidence 是否在合理边界内 (默认 [0.3, 0.85] — 与 insight_generator 一致)

输入:
    actual: dict 含 evidence_refs (list) + confidence (float, optional)
    expected: dict 含
        min_valid_refs: int — 默认 2
        confidence_min: float — 默认 0.3
        confidence_max: float — 默认 0.85
        require_confidence: bool — 是否检查 confidence, 默认 True
    available: dict 含 fact_ids / garmin_dates / diet_dates (各为 set/list)

输出:
    {
        "passed": bool,
        "score": float in [0,1],
        "valid_refs": list,
        "invalid_refs": list,
        "confidence_ok": bool | None,
    }
"""
from __future__ import annotations

from typing import Any, Dict, Iterable


def _validate_refs(
    refs: Iterable[Any],
    fact_ids: set,
    garmin_dates: set,
    diet_dates: set,
) -> tuple[list, list]:
    """复用 insight_generator._gen_llm_pattern_mining 里的 grounding 逻辑."""
    valid, invalid = [], []
    for r in refs or []:
        if not isinstance(r, dict):
            invalid.append(r)
            continue
        rtype = r.get("type")
        if rtype == "fact":
            fid = r.get("id")
            if isinstance(fid, int) and fid in fact_ids:
                valid.append(r)
            else:
                invalid.append(r)
        elif rtype == "garmin_date":
            d = r.get("date")
            if isinstance(d, str) and d in garmin_dates:
                valid.append(r)
            else:
                invalid.append(r)
        elif rtype == "diet_date":
            d = r.get("date")
            if isinstance(d, str) and d in diet_dates:
                valid.append(r)
            else:
                invalid.append(r)
        else:
            invalid.append(r)
    return valid, invalid


def score_grounding(
    actual: Dict[str, Any],
    expected: Dict[str, Any],
    available: Dict[str, Any],
) -> Dict[str, Any]:
    refs = actual.get("evidence_refs") or []
    fact_ids = set(available.get("fact_ids") or [])
    garmin_dates = set(available.get("garmin_dates") or [])
    diet_dates = set(available.get("diet_dates") or [])

    valid, invalid = _validate_refs(refs, fact_ids, garmin_dates, diet_dates)

    min_valid = int(expected.get("min_valid_refs", 2))
    refs_ok = len(valid) >= min_valid

    confidence_ok = None
    if expected.get("require_confidence", True):
        c = actual.get("confidence")
        if c is None:
            confidence_ok = False
        else:
            try:
                cf = float(c)
                cmin = float(expected.get("confidence_min", 0.3))
                cmax = float(expected.get("confidence_max", 0.85))
                confidence_ok = cmin <= cf <= cmax
            except (TypeError, ValueError):
                confidence_ok = False

    passed = refs_ok and (confidence_ok is not False)

    if refs:
        ground_score = len(valid) / len(refs)
    else:
        ground_score = 0.0
    score = ground_score
    if confidence_ok is False:
        score *= 0.5

    return {
        "passed": passed,
        "score": round(score, 3),
        "valid_refs": valid,
        "invalid_refs": invalid,
        "valid_count": len(valid),
        "min_required": min_valid,
        "confidence_ok": confidence_ok,
    }
