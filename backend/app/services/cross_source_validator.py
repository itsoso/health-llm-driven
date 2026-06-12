# -*- coding: utf-8 -*-
"""跨源异常检测 —— 三台设备(Garmin / Apple Watch / RingConn)同指标差异过大时标记。

同时戴多台设备时,同一指标的窗口均值本应接近(消费级算法差异属正常范围)。当某一源
明显偏离其余源时,往往意味着:佩戴位移松动 / 硬件故障 / 该源算法对此人不适配
→ 数据可疑,该指标应暂以高优先级源为准。

诚实原则:
  - 这里只标"哪一源偏离群体",不判它"绝对错"——消费级穿戴各家算法不同。
  - 仅 ≥2 源有同期数据才比(单源无从跨源)。
  - 只读、user_id 隔离,取数复用 ``device_comparison`` 的窗口聚合(不自己写 SQL)。

判定阈值(纯函数 ``flag_outliers``,可独立测试):
  - REL_SPREAD_THRESHOLD = 0.30:极差/均值 > 30% → 跨源差异过大,产出异常。
  - outlier_source = 偏离群体均值最大的源;deviation_pct 带符号(正=偏高,负=偏低)。

为什么不用标准差(σ):本场景设备数通常是 2-3 台。n=3 时单个 outlier 的 z-score
数学上限 ≈ √2 (n=4 是 √3),pstdev 又被 outlier 自身抬高,>2σ 阈值在 3 台设备下
几乎永不触发 → σ 检测对真实使用场景是死代码。极差/均值比例对小样本更直接可靠。
"""
from __future__ import annotations

import logging
from statistics import mean
from typing import Any, Optional

from app.services.device_comparison_service import device_comparison
from app.services.device_source_priority import priority_for

logger = logging.getLogger(__name__)

# 极差/均值 比例阈值:超过即认为各源差异过大。
REL_SPREAD_THRESHOLD = 0.30

# 指标 → 人话标签(与 device_comparison 的 metric key 对齐)。
_METRIC_LABEL = {
    "hrv": "HRV",
    "resting_heart_rate": "静息心率",
    "sleep_score": "睡眠评分",
    "vo2max_running": "VO2max",
    "spo2_avg": "SpO2",
    "steps": "步数",
}

# 源 → 人话名(展示用)。
_SOURCE_LABEL = {
    "garmin": "Garmin",
    "apple-watch": "Apple Watch",
    "ringconn": "RingConn",
    "oura": "Oura",
    "withings-app": "Withings",
}


def _src_label(src: str) -> str:
    return _SOURCE_LABEL.get(src, src)


def _trusted_source(metric: str, present_sources: list[str]) -> Optional[str]:
    """该指标在场源中优先级最高的源 —— "暂以谁为准"。"""
    for src in priority_for(metric):
        if src in present_sources:
            return src
    return present_sources[0] if present_sources else None


def flag_outliers(metric: str, by_source: dict[str, float]) -> Optional[dict[str, Any]]:
    """纯函数:对单指标的 {source: 窗口均值} 判定是否跨源异常。

    返回异常 dict 或 None(无异常 / 不足两源 / 均值为 0 无法算比例)。
    """
    present = {s: float(v) for s, v in by_source.items() if v is not None}
    if len(present) < 2:
        return None

    vals = list(present.values())
    avg = mean(vals)
    if avg == 0:
        return None  # 均值为 0 无法算相对偏离,避免除零

    spread = max(vals) - min(vals)
    rel_spread = spread / abs(avg)
    if rel_spread <= REL_SPREAD_THRESHOLD:
        return None

    # outlier = 偏离群体均值最大的源
    outlier_source = max(present, key=lambda s: abs(present[s] - avg))
    outlier_val = present[outlier_source]
    deviation_pct = round((outlier_val - avg) / abs(avg) * 100, 1)

    trusted = _trusted_source(metric, list(present.keys()))
    label = _METRIC_LABEL.get(metric, metric)
    direction = "高" if deviation_pct > 0 else "低"
    hint = (
        f"{_src_label(outlier_source)} 的{label}窗口均值比各源平均{direction} "
        f"{abs(deviation_pct)}%,可能佩戴松动/位移或算法差异,"
        f"该指标暂以 {_src_label(trusted)} 为准。"
    )

    return {
        "metric": metric,
        "label": label,
        "sources": {s: round(v, 2) for s, v in present.items()},
        "mean": round(avg, 2),
        "outlier_source": outlier_source,
        "deviation_pct": deviation_pct,
        "rel_spread": round(rel_spread, 3),
        "trusted_source": trusted,
        "hint": hint,
    }


def detect_cross_source_anomalies(db, user_id: int, days: int = 7) -> list[dict[str, Any]]:
    """近 days 天,对每个有 ≥2 源的指标做跨源异常检测。

    只读;复用 ``device_comparison`` 的窗口聚合取数。DB 异常 rollback 并抛出(不静默吞),
    让调用方(specialist)自己包 try 决定降级文案。
    """
    try:
        comparison = device_comparison(db, user_id, days=days)
    except Exception:
        # 取数失败:回滚事务,把异常往上抛(不假装无异常)。
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("[cross_source] rollback 失败", exc_info=True)
        raise

    anomalies: list[dict[str, Any]] = []
    for comp in comparison.get("comparisons", []):
        by_source = comp.get("by_source") or {}
        flagged = flag_outliers(comp.get("metric", ""), by_source)
        if flagged is not None:
            anomalies.append(flagged)

    # 偏离越大越靠前
    anomalies.sort(key=lambda a: abs(a["deviation_pct"]), reverse=True)
    return anomalies
