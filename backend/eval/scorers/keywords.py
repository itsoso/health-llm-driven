"""Keyword scorer — 必含/必不含关键词检查.

适用: Orchestrator 合成回答 (e.g. 「必须提到 readiness」「不能出现"诊断"」).
"""
from __future__ import annotations

from typing import Any, Dict


def score_keywords(actual: str, expected: Dict[str, Any]) -> Dict[str, Any]:
    """expected 字段:
        must_contain: list[str] — 这些词必须 (case-insensitive 子串) 出现
        must_contain_any: list[str] — 这些语义替代词至少出现一个
        must_not_contain: list[str] — 这些词必须不出现 (e.g. "诊断" / "确诊")

    输出 passed = 全部必含命中 + 任一替代词命中 + 全部禁词缺席.
    score = 命中率 (0..1) 的简单平均.
    """
    must = expected.get("must_contain", []) or []
    must_any = expected.get("must_contain_any", []) or []
    forbidden = expected.get("must_not_contain", []) or []
    actual_lc = (actual or "").lower()

    present = [w for w in must if w.lower() in actual_lc]
    missing = [w for w in must if w.lower() not in actual_lc]
    any_present = [w for w in must_any if w.lower() in actual_lc]
    leaked = [w for w in forbidden if w.lower() in actual_lc]

    passed = (not missing) and (not must_any or bool(any_present)) and (not leaked)
    required_groups = len(must) + bool(must_any)
    matched_groups = len(present) + bool(any_present)
    if required_groups:
        recall = matched_groups / required_groups
    else:
        recall = 1.0
    forbidden_penalty = 0.0 if not leaked else len(leaked) / max(len(forbidden), 1)
    score = max(0.0, recall - forbidden_penalty)

    return {
        "passed": passed,
        "score": round(score, 3),
        "present": present,
        "missing": missing,
        "any_present": any_present,
        "leaked": leaked,
    }
