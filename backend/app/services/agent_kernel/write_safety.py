"""Shared fail-closed checks for user-authored write language."""
from __future__ import annotations

import re


_EXPLICIT_WRITE_CANCELLATION_RE = re.compile(
    r"(?:先不要|暂不|不需要|不要|不用|无需|先别|别|不)"
    r"(?:再|先|想|要|帮我|给我|把|将|这|该|本|这次|本次|"
    r"早餐|午餐|晚餐|加餐|饮食|一餐|这餐|条|份|个|次|"
    r"[\s，,。.!！；;：:])*"
    r"(?:记录|记一下|记下|记|保存|录入|写入|写回|添加|加到饮食)"
)


def is_explicit_write_cancellation(text: str) -> bool:
    """Match cancellation of a write action without matching food modifiers."""
    normalized = str(text or "").strip()
    return bool(
        _EXPLICIT_WRITE_CANCELLATION_RE.search(normalized)
        or re.search(
            r"(?:取消|撤销)(?:这次|本次|该次)?(?:记录|保存|录入|写入)",
            normalized,
        )
        or re.search(
            r"(?:记录|保存|录入|写入)(?:这次|本次|该次)?(?:取消|撤销|算了)",
            normalized,
        )
    )
