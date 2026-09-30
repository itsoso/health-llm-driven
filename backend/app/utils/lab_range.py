"""化验参考范围方向解析(纯函数,无 DB/注册副作用)。

供 Safety Guardian DSI 规则与 SupplementAdvisor 共用:flagged_abnormal 只说明"异常",
不说明方向;需要"偏低"语义的调用方必须经此判向,不可把"异常"当"偏低"。
"""
from __future__ import annotations

import re
from typing import Optional


def is_below_range(value, reference_range) -> Optional[bool]:
    """value < 参考下限 → True;> 下限/无法判向 → False;不可解析或缺值 → None。"""
    if value is None or not reference_range:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    rr = str(reference_range)
    # lo-hi:兼容多种分隔符(ASCII - ~、全角 ～－、中文 至、en/em dash);收紧数字 token 防误锚
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~～–—－至]\s*(\d+(?:\.\d+)?)", rr)
    if m:
        return v < float(m.group(1))
    # 仅下限:≥X / >X / >=X
    m2 = re.search(r"[≥>＞]\s*=?\s*(\d+(?:\.\d+)?)", rr)
    if m2:
        return v < float(m2.group(1))
    return None  # 不可解析(如 "<X"、纯文字) → 交调用方保守兜底,不静默当正常
