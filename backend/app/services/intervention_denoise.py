"""R16 P2 —— 干预结局端点去噪(算 delta/显著性**之前**先平滑,防单点噪声冒充信号)。

结构性不诚实(本模块修):`record_recheck` 用 baseline_value/latest_value 两个**单点**观测算 delta,
RCV(`classify_change`)再对这个本身没去噪的单点 delta 判显著 —— 单次化验/单日测量的随机噪声
被当成真干预效果。本模块在算 delta 前先平滑端点:

- **密集**(锚点 ±7 天窗内各 ≥MIN_POINTS 个观测)→ 端点取 7 天均值(`method='7d_ma'`)。
- **稀疏**(化验:窗内 <MIN_POINTS)→ **不平滑**(`method='none'`)+ 调用方据此把置信度封 low
  (单点不臆造趋势)。两端只要一端稀疏就整体 none(不混用)。
- **MA-lag 背离守卫**(under-alarm):最新原始点相对其 30 天窗 robust-Z(median+MAD)很大
  → 近期波动剧烈、平滑可能洗掉真信号 → 标 `ma_lag_divergent`,调用方据此封 low(只降不升),
  不静默给「flat 高置信」。MAD=0(序列恒定)→ robust-Z 不可算 → 返回 None(不误判背离)。

纯统计、**基因无关**(不 import 任何 genetic / twin / snp)。所有时间统一按 UTC 比较(naive 当 UTC)。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

MIN_POINTS = 3          # 端点窗内 ≥3 点才平滑(否则稀疏,不臆造趋势)
MA_WINDOW_DAYS = 7      # 端点平滑窗(锚点 ±天)
Z_WINDOW_DAYS = 30      # MA-lag 背离的 robust-Z 回看窗
DIVERGENCE_Z = 3.0      # 最新原始点 robust-Z 超此 → 近期剧烈波动
_MAD_TO_SD = 1.4826     # MAD → 正态一致化标准差

Point = Tuple[Optional[datetime], Optional[float]]


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _clean(series: Sequence[Point]) -> List[Tuple[datetime, float]]:
    out: List[Tuple[datetime, float]] = []
    for t, v in series:
        tu = _utc(t)
        if tu is not None and v is not None:
            out.append((tu, float(v)))
    return out


def window_mean(
    series: Sequence[Point], anchor: Optional[datetime], window_days: int = MA_WINDOW_DAYS
) -> Tuple[Optional[float], int]:
    """锚点 ±window_days 内观测的均值 + 点数。无锚点/无点 → (None, 0)。"""
    a = _utc(anchor)
    if a is None:
        return None, 0
    lo, hi = a - timedelta(days=window_days), a + timedelta(days=window_days)
    vals = [v for (t, v) in _clean(series) if lo <= t <= hi]
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)


def robust_z(
    series: Sequence[Point], value: Optional[float], anchor: Optional[datetime],
    lookback_days: int = Z_WINDOW_DAYS,
) -> Optional[float]:
    """value 相对锚点前 lookback 窗的 median+MAD 的稳健 Z。点不足 / MAD=0 → None(不判背离,防除零)。"""
    a = _utc(anchor)
    if value is None or a is None:
        return None
    lo = a - timedelta(days=lookback_days)
    vals = [v for (t, v) in _clean(series) if lo <= t <= a]
    if len(vals) < MIN_POINTS:
        return None
    med = median(vals)
    mad = median([abs(v - med) for v in vals])
    if mad < 1e-9:            # 序列恒定 → MAD=0 → 不可算 Z(除零守卫)
        return None
    return (float(value) - med) / (_MAD_TO_SD * mad)


def denoise_endpoints(
    series: Sequence[Point],
    baseline_anchor: Optional[datetime], baseline_raw: Optional[float],
    latest_anchor: Optional[datetime], latest_raw: Optional[float],
) -> Dict[str, Any]:
    """返回 {baseline, latest, method, sample_n, ma_lag_divergent}。

    method='7d_ma':两端各 ≥MIN_POINTS → baseline/latest 为各自 7 天均值;否则 'none' 用原始单点。
    ma_lag_divergent:仅 7d_ma 时评估 —— 最新原始点 robust-Z ≥ DIVERGENCE_Z(近期剧烈波动)。
    """
    b_sm, b_n = window_mean(series, baseline_anchor)
    l_sm, l_n = window_mean(series, latest_anchor)

    # 短周期守卫(对抗评审 BLOCKING):两锚点间隔 < 2×窗 → 两端 ±MA_WINDOW_DAYS 窗重叠,**同一批观测
    # 同时喂基线与复查端**,平滑后 delta 被拉向 0 → 真改善被误判 flat(under-detection,正是本模块要防的
    # 反方向)。此时无法诚实做端点平滑 → 退回原始单点(method=none)+ 后续置信度封 low(短周期不臆造)。
    ba, la = _utc(baseline_anchor), _utc(latest_anchor)
    windows_overlap = (
        ba is not None and la is not None
        and abs((la - ba).total_seconds()) < 2 * MA_WINDOW_DAYS * 86400
    )

    if (
        not windows_overlap
        and b_n >= MIN_POINTS and l_n >= MIN_POINTS
        and b_sm is not None and l_sm is not None
    ):
        method, baseline, latest = "7d_ma", b_sm, l_sm
    else:
        method, baseline, latest = "none", baseline_raw, latest_raw

    divergent = False
    if method == "7d_ma" and latest_raw is not None:
        z = robust_z(series, latest_raw, latest_anchor)
        divergent = z is not None and abs(z) >= DIVERGENCE_Z

    return {
        "baseline": baseline,
        "latest": latest,
        "method": method,
        "sample_n": min(b_n, l_n),
        "ma_lag_divergent": divergent,
    }


def smoothed_delta_pct(d: Dict[str, Any]) -> Optional[float]:
    """从 denoise_endpoints 结果算去噪 delta%(仅 7d_ma 有意义;none → None 让调用方退回原始)。"""
    if d.get("method") != "7d_ma":
        return None
    base, latest = d.get("baseline"), d.get("latest")
    if base is None or latest is None or abs(base) < 1e-9:
        return None
    return round((latest - base) / abs(base) * 100, 1)
