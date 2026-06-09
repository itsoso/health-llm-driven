# -*- coding: utf-8 -*-
"""双设备一致性对比 —— 同时戴 Apple Watch + Garmin 时,同指标并排比 + 一致度。

数据层早已支持多源共存(GarminData.data_source + (user,date,source) 唯一索引),
两台设备同一天各存一行。本服务把它们按指标分组对比:
  - by_source: 每台设备该指标的窗口均值
  - diff: 设备间差值
  - agreement: 一致度(1=完全一致)→ 连到"数据质量/置信度":两台越一致越可信

诚实:消费级穿戴 HRV/睡眠算法各家不同,差异正常;agreement 仅描述一致性,不判谁"对"。
不足两台数据 → 不对比(不编造)。
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

# (字段, 中文名, 单位, 小数位)
_COMPARE_METRICS = [
    ("hrv", "HRV", "ms", 1),
    ("resting_heart_rate", "静息心率", "bpm", 0),
    ("sleep_score", "睡眠评分", "", 0),
    ("vo2max_running", "VO2max", "", 1),
    ("spo2_avg", "SpO2", "%", 1),
    ("steps", "步数", "", 0),
]


def compare_sources(values_by_source: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """对 {source: {metric: 值}} 逐指标对比(纯函数,可测)。

    只比 ≥2 个来源都有的指标;agreement=1-(极差/均值),clamp [0,1]。
    """
    out: list[dict[str, Any]] = []
    for key, label, unit, nd in _COMPARE_METRICS:
        present = {
            s: vals[key] for s, vals in values_by_source.items()
            if vals.get(key) is not None
        }
        if len(present) < 2:
            continue
        nums = list(present.values())
        mx, mn = max(nums), min(nums)
        mean = sum(nums) / len(nums)
        spread = mx - mn
        agreement = round(max(0.0, min(1.0, 1 - spread / mean)), 3) if mean else None
        out.append({
            "metric": key,
            "label": label,
            "unit": unit,
            "by_source": {s: round(v, nd) for s, v in present.items()},
            "diff": round(spread, nd),
            "agreement": agreement,
        })
    return out


def device_comparison(db, user_id: int, days: int = 7) -> dict[str, Any]:
    """近 days 天,按 data_source 分组做同指标对比(窗口均值)。"""
    from app.models.daily_health import GarminData
    from app.utils.timezone import get_china_today

    cutoff = get_china_today() - timedelta(days=days)
    rows = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id, GarminData.record_date >= cutoff)
        .all()
    )

    acc: dict[str, dict[str, list]] = {}
    for r in rows:
        src = r.data_source or "garmin"
        m = acc.setdefault(src, {})
        for key, *_ in _COMPARE_METRICS:
            v = getattr(r, key, None)
            if v is not None:
                m.setdefault(key, []).append(float(v))

    values_by_source = {
        src: {k: sum(vs) / len(vs) for k, vs in metrics.items() if vs}
        for src, metrics in acc.items()
    }
    comparisons = compare_sources(values_by_source)
    return {
        "sources": sorted(values_by_source.keys()),
        "window_days": days,
        "comparisons": comparisons,
        "note": (
            "窗口均值对比;agreement 仅描述设备一致性,不判谁更准(各家算法不同)。"
            if comparisons else "需 ≥2 个来源(如 Apple Watch + Garmin)同期数据才能对比。"
        ),
    }


# 每源摘要要展示的指标 (key → GarminData 列名). 取窗口内最近一条非空值.
_SUMMARY_METRICS = [
    "steps",
    "resting_heart_rate",
    "avg_heart_rate",
    "hrv",
    "total_sleep_duration",
    "sleep_score",
    "spo2_avg",
    "spo2_min",
    "active_calories",
    "distance_meters",
]


def sources_summary(db, user_id: int, days: int = 30) -> dict[str, Any]:
    """近 days 天每个 data_source 的覆盖与最新指标快照.

    每源:
      - days_covered: 窗口内 distinct record_date 数
      - latest_date:  窗口内最新一天
      - metrics:      每指标取窗口内"最近一天的非空值" (按 record_date 倒序第一个非空)
    按 days_covered 降序排列 (主力设备在前).
    """
    from app.models.daily_health import GarminData
    from app.utils.timezone import get_china_today

    cutoff = get_china_today() - timedelta(days=days)
    rows = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id, GarminData.record_date >= cutoff)
        # 最新日期在前 → 每指标第一个非空即"最近值"
        .order_by(GarminData.record_date.desc())
        .all()
    )

    by_source: dict[str, dict[str, Any]] = {}
    for r in rows:
        src = r.data_source or "garmin"
        agg = by_source.setdefault(
            src, {"dates": set(), "latest_date": None, "metrics": {}}
        )
        agg["dates"].add(r.record_date)
        if agg["latest_date"] is None or r.record_date > agg["latest_date"]:
            agg["latest_date"] = r.record_date
        for key in _SUMMARY_METRICS:
            if key in agg["metrics"]:
                continue  # 已拿到更近的非空值 (rows 已按日期倒序)
            v = getattr(r, key, None)
            if v is not None:
                agg["metrics"][key] = v

    out_sources = [
        {
            "data_source": src,
            "days_covered": len(agg["dates"]),
            "latest_date": agg["latest_date"].isoformat() if agg["latest_date"] else None,
            "metrics": agg["metrics"],
        }
        for src, agg in by_source.items()
    ]
    out_sources.sort(key=lambda s: s["days_covered"], reverse=True)
    return {"window_days": days, "sources": out_sources}
