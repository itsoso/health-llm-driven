"""展示用数字格式化 —— 研发要求: 面向用户可见的数字最多保留 2 位小数。

规则(见 AGENTS.md §14):
  - 整数保持整数(58 → 58,不写 58.0)。
  - 小数最多保留 2 位:四舍五入到 2 位后去掉尾零,按实际精度决定
    (71.4 → 71.4、6.166666… → 6.17、58.0 → 58、6.10 → 6.1)。
  - bool / 非数字 / NaN / Inf 原样返回(不误伤)。

**只作用于展示层**(卡片 / 表格 / 图表标签等面向用户的数字);**不改写入库/记录路径的
原始精度**(那是数据完整性,与展示精度是两回事)。
"""
from __future__ import annotations

import math
from typing import Any

_MAX_DECIMALS = 2


def format_display_number(value: Any) -> Any:
    """整数→整数;小数→最多 2 位(去尾零)。bool/非数字/NaN/Inf 原样返回。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        return value
    rounded = round(float(value), _MAX_DECIMALS)
    return int(rounded) if rounded == int(rounded) else rounded


def format_card_numbers(obj: Any) -> Any:
    """递归把 dict/list/tuple 里的数字规范成展示精度(≤2 位小数)。字符串/其他原样。

    用于卡片 payload 的展示口径统一(单一 choke point 一次搞定所有卡片所有字段)。
    """
    if isinstance(obj, dict):
        return {k: format_card_numbers(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [format_card_numbers(v) for v in obj]
    return format_display_number(obj)
