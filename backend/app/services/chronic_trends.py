"""慢病趋势引擎(通用,纯函数)。

复用于:肝酶(ALT/GGT)、鼻炎喷嚏数、体重、睡眠分等任何"看长期趋势"的指标。
现状(盘点结论):产品基础设施全,但慢病只做当日快照、不看趋势 —— 库里的历史
数据(如 8 年肝酶)没人消费。这层把"一串时间点 → 方向/变化幅度"标准化,
让 specialist / API / 对话都能引用,且**只描述事实趋势,不下诊断**。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

Direction = Literal["rising", "falling", "flat"]
Verdict = Literal["improving", "worsening", "stable"]


@dataclass
class Trend:
    n: int                      # 数据点数
    first_value: float
    last_value: float
    first_date: date
    last_date: date
    abs_change: float           # last - first
    pct_change: Optional[float]  # (last-first)/|first| ×100;first=0 时 None
    direction: Direction        # 数值方向
    span_days: int

    def verdict(self, higher_is_worse: bool, flat_pct: float = 5.0) -> Verdict:
        """结合"高了是好是坏"给出好转/恶化/平稳判断。

        higher_is_worse=True(如 ALT/GGT/体重/喷嚏):升=恶化。
        变化幅度 < flat_pct% 视为平稳,避免噪声当趋势。
        """
        if self.pct_change is None or abs(self.pct_change) < flat_pct:
            return "stable"
        rising = self.pct_change > 0
        worse = rising if higher_is_worse else not rising
        return "worsening" if worse else "improving"


def compute_trend(points: list[tuple[date, float]]) -> Optional[Trend]:
    """一串 (日期, 值) → Trend。不足 2 点返回 None(无法成趋势,不臆测)。

    入参无需有序;内部按日期排序。值为 None 的点应由调用方先过滤。
    """
    clean = [(d, v) for d, v in points if d is not None and v is not None]
    if len(clean) < 2:
        return None
    clean.sort(key=lambda p: p[0])
    (fd, fv), (ld, lv) = clean[0], clean[-1]
    abs_change = lv - fv
    pct = (abs_change / abs(fv) * 100.0) if fv != 0 else None
    if abs_change > 0:
        direction: Direction = "rising"
    elif abs_change < 0:
        direction = "falling"
    else:
        direction = "flat"
    return Trend(
        n=len(clean), first_value=fv, last_value=lv, first_date=fd, last_date=ld,
        abs_change=round(abs_change, 2),
        pct_change=round(pct, 1) if pct is not None else None,
        direction=direction, span_days=(ld - fd).days,
    )


def adherence_rate(taken_days: int, expected_days: int) -> Optional[float]:
    """用药依从率 = 实际服用天数 / 应服天数(0–1)。expected<=0 返回 None。"""
    if expected_days <= 0:
        return None
    return round(min(taken_days / expected_days, 1.0), 3)


def describe_trend(label: str, t: Trend, unit: str = "", higher_is_worse: bool = True) -> str:
    """一行人话趋势描述(给 LLM / UI 用)。"""
    v = t.verdict(higher_is_worse)
    arrow = {"rising": "↑", "falling": "↓", "flat": "→"}[t.direction]
    tag = {"improving": "好转", "worsening": "恶化", "stable": "平稳"}[v]
    pct = f"{t.pct_change:+.0f}%" if t.pct_change is not None else "—"
    return (f"{label}: {t.first_value:g}{unit}({t.first_date:%Y-%m}) {arrow} "
            f"{t.last_value:g}{unit}({t.last_date:%Y-%m}),{pct} · {tag}")
