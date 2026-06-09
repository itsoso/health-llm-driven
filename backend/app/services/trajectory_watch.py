# -*- coding: utf-8 -*-
"""主动化推广 —— 泛型指标轨迹监测(把 longevity_watch 模式推广到代谢/心血管)。

longevity_watch 证明了"跨快照 diff → 改善庆祝 / 回退温和提醒"的主动 Agent 模式;
本模块把它**泛化成配置驱动**:任一 twin_json 路径上的指标都能监测,方向复用
metrics.HIGHER_IS_BETTER(单一真值源),阈值按指标配。新增 recovery/safety 指标 = 改配置。

纯逻辑(无 DB/通知/Celery 依赖),可全测;任务层 tasks/trajectory_watch.py 负责取数+推送+埋点。
诚实:跨快照变化是用户自身趋势,非人群阈值;回退提醒不报警化;缺值不打扰。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from app.tasks.metrics import HIGHER_IS_BETTER

# 监测清单:twin_json 路径 + 展示名 + 单位 + 显著变化阈值(相对 %)
# 方向(越高/越低好)复用 metrics.HIGHER_IS_BETTER,不在此重复定义。
WATCH_METRICS: List[dict] = [
    {"key": "weight", "path": ("body_composition", "weight_kg"), "label": "体重", "unit": "kg", "pct": 0.03},
    {"key": "blood_glucose", "path": ("labs", "blood_glucose"), "label": "空腹血糖", "unit": "mmol/L", "pct": 0.05},
    {"key": "hba1c", "path": ("labs", "hba1c"), "label": "糖化血红蛋白", "unit": "%", "pct": 0.05},
    {"key": "ldl", "path": ("labs", "ldl"), "label": "低密度脂蛋白", "unit": "mmol/L", "pct": 0.05},
    {"key": "systolic_bp", "path": ("labs", "blood_pressure_systolic"), "label": "收缩压", "unit": "mmHg", "pct": 0.05},
]


@dataclass(frozen=True)
class MetricChange:
    metric: str
    label: str
    prev: float
    curr: float
    delta_pct: float       # (curr-prev)/|prev|;方向无关的原始变化
    kind: str              # improved / regressed / stable
    notable: bool
    title: str
    message: str


def _dig(twin_json: Any, path: tuple) -> Optional[float]:
    cur: Any = twin_json
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return float(cur) if isinstance(cur, (int, float)) else None


def diff_metric(prev_json: Any, curr_json: Any, spec: dict) -> Optional[MetricChange]:
    """单指标跨快照变化。缺值/基线为 0 → None。"""
    prev = _dig(prev_json, spec["path"])
    curr = _dig(curr_json, spec["path"])
    if prev is None or curr is None or prev == 0:
        return None
    pct = (curr - prev) / abs(prev)
    higher_better = HIGHER_IS_BETTER.get(spec["key"], False)
    toward_good = pct if higher_better else -pct  # 正 = 朝好的方向
    thr = spec.get("pct", 0.05)
    notable = abs(pct) >= thr
    label = spec["label"]
    if toward_good >= thr:
        kind, title = "improved", f"🎉 你的{label}在改善"
        message = f"{label}从 {round(prev,1)} 变到 {round(curr,1)} {spec.get('unit','')},朝目标方向。保持住。"
    elif toward_good <= -thr:
        kind, title = "regressed", f"你的{label}有点波动"
        message = f"{label}从 {round(prev,1)} 变到 {round(curr,1)} {spec.get('unit','')}。不用慌,看看最近的生活方式——可逆。"
    else:
        kind, title = "stable", f"{label}基本持平"
        message = f"{label}从 {round(prev,1)} 到 {round(curr,1)},变化不大。"
    return MetricChange(
        metric=spec["key"], label=label, prev=round(prev, 1), curr=round(curr, 1),
        delta_pct=round(pct, 4), kind=kind, notable=notable, title=title, message=message,
    )


def scan_trajectories(snapshots_newest_first: List[Any]) -> List[MetricChange]:
    """对每个 WATCH_METRIC,挑最新+更早(值不同)两快照算变化,返回 notable 的。"""
    out: List[MetricChange] = []
    for spec in WATCH_METRICS:
        curr_snap = None
        for snap in snapshots_newest_first:
            if _dig(snap, spec["path"]) is None:
                continue
            if curr_snap is None:
                curr_snap = snap
                continue
            ch = diff_metric(snap, curr_snap, spec)  # (prev=older, curr=newer)
            if ch and ch.prev != ch.curr and ch.notable:
                out.append(ch)
            break
    return out
