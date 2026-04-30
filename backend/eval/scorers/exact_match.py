"""Exact match scorer — 集合命中.

适用: Safety Guardian 这类「应该触发哪些 rule_id」的 ground truth 评估.

输入:
    actual: set[str] — 实际触发的 rule_id 集合
    expected: dict 含 must_fire / must_not_fire / dont_care
        must_fire: list[str] — 这些必须命中 (缺一即 fail)
        must_not_fire: list[str] — 这些必须不命中 (出现一个即 fail)
        dont_care: list[str] — 出现/不出现都行 (默认不写就是 dont_care)

输出:
    {
        "passed": bool,                  # must_fire 全中 + must_not_fire 全不中
        "score": float,                  # F1 in [0, 1]
        "missing": list[str],            # must_fire 中没触发的
        "unexpected": list[str],         # must_not_fire 但触发了的
        "matched": list[str],            # 正确触发的
    }
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


def score_rule_set(actual: Iterable[str], expected: Dict[str, Any]) -> Dict[str, Any]:
    actual_set = set(actual)
    must_fire = set(expected.get("must_fire", []) or [])
    must_not_fire = set(expected.get("must_not_fire", []) or [])

    matched = sorted(must_fire & actual_set)
    missing = sorted(must_fire - actual_set)
    unexpected = sorted(must_not_fire & actual_set)

    passed = (not missing) and (not unexpected)

    if must_fire:
        precision_denom = len(matched) + len(unexpected)
        precision = len(matched) / precision_denom if precision_denom else 1.0
        recall = len(matched) / len(must_fire)
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
    else:
        # must_fire 为空时, 只用 unexpected 是否为空判定
        f1 = 0.0 if unexpected else 1.0

    return {
        "passed": passed,
        "score": round(f1, 3),
        "matched": matched,
        "missing": missing,
        "unexpected": unexpected,
    }
