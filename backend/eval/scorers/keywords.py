"""Keyword scorer — 必含/必不含关键词检查.

适用: Orchestrator 合成回答 (e.g. 「必须提到 readiness」「不能出现"诊断"」).
"""
from __future__ import annotations

from typing import Any, Dict


def score_keywords(actual: str, expected: Dict[str, Any]) -> Dict[str, Any]:
    """expected 字段:
        must_contain: list[str] — 这些词必须 (case-insensitive 子串) 出现
        must_not_contain: list[str] — 这些词必须不出现 (e.g. "诊断" / "确诊")

    开放式自然语言语义断言不在这里用正则猜测；交给 llm_judge_assertions.
    输出 passed = 全部必含命中 + 全部禁词缺席.
    score = 命中率 (0..1) 的简单平均.
    """
    must = expected.get("must_contain", []) or []
    forbidden = expected.get("must_not_contain", []) or []
    actual_lc = (actual or "").lower()

    present = [w for w in must if w.lower() in actual_lc]
    missing = [w for w in must if w.lower() not in actual_lc]
    leaked = [w for w in forbidden if w.lower() in actual_lc]

    passed = (not missing) and (not leaked)
    if must:
        recall = len(present) / len(must)
    else:
        recall = 1.0
    forbidden_penalty = 0.0 if not leaked else len(leaked) / max(len(forbidden), 1)
    score = max(0.0, recall - forbidden_penalty)

    return {
        "passed": passed,
        "score": round(score, 3),
        "present": present,
        "missing": missing,
        "leaked": leaked,
    }
