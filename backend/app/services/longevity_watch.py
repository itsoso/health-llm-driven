# -*- coding: utf-8 -*-
"""抗衰主动 Agent —— 生物年龄跨快照变化检测(纯逻辑,Phase2 W1 brain)。

输入两次 Twin 快照的 twin_json(无 DB/Celery/通知依赖,可单测),输出"是否值得
主动提醒"的结构化变化。任务层(app/tasks/longevity_watch.py)负责取快照 + 推送 + 埋点。

诚实纪律:
- 只在变化"显著"(≥ NOTABLE_YEARS)时才 notable=True → 任务层据此决定推不推(打扰预算)
- 优先 PhenoAge(validated),回退 Garmin 体能年龄(同 validated);两者都越低越好
- 回退提醒不报警化、指向四件套;改善给正反馈
- 缺可比数据 → 返回 None(不猜、不打扰)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

# 变化达到这个岁数才值得主动打扰(避免噪声 / 测量抖动)
NOTABLE_YEARS = 1.0

# 候选生物年龄指标(都"越低越好"):(twin_json 路径, 展示名)
_BIOAGE_METRICS = [
    ("phenotypic_age", ("labs", "phenotypic_age"), "身体年龄"),
    ("fitness_age", ("physiological", "vo2max_fitness_age"), "体能年龄"),
]


@dataclass(frozen=True)
class LongevityChange:
    metric: str          # phenotypic_age / fitness_age
    label: str           # 身体年龄 / 体能年龄
    prev: float
    curr: float
    delta_years: float   # curr - prev(负 = 变年轻 = 改善,因越低越好)
    kind: str            # improved / regressed / stable
    notable: bool        # 是否达到主动打扰阈值
    title: str
    message: str


def _dig(twin_json: Any, path: tuple) -> Optional[float]:
    cur: Any = twin_json
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def diff_biological_age(prev_json: Any, curr_json: Any) -> Optional[LongevityChange]:
    """对两次快照,挑第一个两边都有值的生物年龄指标,算变化。无 → None。"""
    for metric, path, label in _BIOAGE_METRICS:
        prev = _dig(prev_json, path)
        curr = _dig(curr_json, path)
        if prev is None or curr is None:
            continue
        delta = round(curr - prev, 1)
        abs_d = abs(delta)
        notable = abs_d >= NOTABLE_YEARS
        if delta <= -NOTABLE_YEARS:
            kind = "improved"
            title = f"🎉 你的{label}变年轻了"
            message = (
                f"{label}从 {round(prev,1)} 降到 {round(curr,1)} 岁,年轻了 {abs_d:.1f} 岁。"
                "保持当前的睡眠/运动/饮食节奏。(基于血检/设备代理指标,非诊断)"
            )
        elif delta >= NOTABLE_YEARS:
            kind = "regressed"
            title = f"你的{label}有点回升"
            message = (
                f"{label}从 {round(prev,1)} 升到 {round(curr,1)} 岁,涨了 {abs_d:.1f} 岁。"
                "不用慌,看看最近的睡眠/运动/饮食/压力——这些都是可逆的。(代理指标,非诊断)"
            )
        else:
            kind = "stable"
            title = f"{label}基本持平"
            message = f"{label}从 {round(prev,1)} 到 {round(curr,1)} 岁,变化不大。"
        return LongevityChange(
            metric=metric, label=label, prev=round(prev, 1), curr=round(curr, 1),
            delta_years=delta, kind=kind, notable=notable, title=title, message=message,
        )
    return None


def find_change_in_snapshots(snapshots_newest_first: List[Any]) -> Optional[LongevityChange]:
    """从"最新在前"的 twin_json 列表里挑 curr(最新有生物年龄的)与 prev
    (更早一条、值不同的),算变化。不足两条可比 → None。"""
    seen_curr: Optional[Any] = None
    for snap in snapshots_newest_first:
        has_bioage = any(_dig(snap, p) is not None for _, p, _ in _BIOAGE_METRICS)
        if not has_bioage:
            continue
        if seen_curr is None:
            seen_curr = snap
            continue
        change = diff_biological_age(snap, seen_curr)
        # 跳过完全相同(同一次体检重复快照)
        if change is not None and change.prev == change.curr:
            continue
        return change
    return None
