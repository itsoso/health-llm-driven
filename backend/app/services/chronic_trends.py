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


@dataclass
class LagAssociation:
    """事件 → 指标的时滞关联(描述性,**非因果**)。"""
    n_events: int          # 落在该 lag 上、有指标值的事件数
    mean_after: float      # 事件后第 lag 天的指标均值
    mean_baseline: float   # 非事件日的指标均值(对照)
    delta: float           # mean_after - mean_baseline
    pct: Optional[float]   # delta / |baseline| ×100
    lag_days: int

    @property
    def meaningful(self) -> bool:
        """样本足够(≥3 事件)且变化幅度 ≥10% 才算值得提的关联。"""
        return self.n_events >= 3 and self.pct is not None and abs(self.pct) >= 10.0


def lag_association(
    event_dates: list[date],
    series: list[tuple[date, float]],
    lag_days: int,
) -> Optional[LagAssociation]:
    """计算"事件后第 lag 天"的指标均值 vs 对照(非事件相关日)均值。

    描述性关联,**不声称因果**(N=1 个体数据,只看趋势倾向)。
    event_dates: 事件发生的日期(如饮酒日 / 高 AQI 日)。
    series: 指标 (日期, 值)。lag_days: 事件后第几天看指标(0=当天,1=次日)。
    不足以计算(无事件后数据 / 无对照)→ None。
    """
    by_date: dict[date, float] = {}
    for d, v in series:
        if d is not None and v is not None:
            by_date[d] = v  # 同日多值时后者覆盖
    if not by_date or not event_dates:
        return None

    from datetime import timedelta
    after_dates = {e + timedelta(days=lag_days) for e in event_dates}
    after_vals = [by_date[d] for d in after_dates if d in by_date]
    baseline_vals = [v for d, v in by_date.items() if d not in after_dates]
    if not after_vals or not baseline_vals:
        return None

    mean_after = sum(after_vals) / len(after_vals)
    mean_base = sum(baseline_vals) / len(baseline_vals)
    delta = mean_after - mean_base
    pct = (delta / abs(mean_base) * 100.0) if mean_base != 0 else None
    return LagAssociation(
        n_events=len(after_vals),
        mean_after=round(mean_after, 1), mean_baseline=round(mean_base, 1),
        delta=round(delta, 1), pct=round(pct, 1) if pct is not None else None,
        lag_days=lag_days,
    )


def describe_trend(label: str, t: Trend, unit: str = "", higher_is_worse: bool = True) -> str:
    """一行人话趋势描述(给 LLM / UI 用)。"""
    v = t.verdict(higher_is_worse)
    arrow = {"rising": "↑", "falling": "↓", "flat": "→"}[t.direction]
    tag = {"improving": "好转", "worsening": "恶化", "stable": "平稳"}[v]
    pct = f"{t.pct_change:+.0f}%" if t.pct_change is not None else "—"
    return (f"{label}: {t.first_value:g}{unit}({t.first_date:%Y-%m}) {arrow} "
            f"{t.last_value:g}{unit}({t.last_date:%Y-%m}),{pct} · {tag}")
