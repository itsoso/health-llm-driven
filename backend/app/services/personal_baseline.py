"""Personal rolling baseline + deviation detection (Phase 0, pure statistics).

设计文档: docs/design-personal-predictive-model.md §4 Phase 0.

核心范式: per-metric **个人滚动基线** + 当前值偏离 (z-score) + 趋势。
**不是预测未来, 是"你现在 vs 你自己的基线"。** 纯统计, 无 LLM, 无 ML 依赖
(只用标准库 ``statistics``)。

与已上线的跨源异常 (#149, ``cross_source_validator``) 互补:
  - #149 = 同一天**设备之间**同指标差异 (佩戴位移 / 硬件故障)。
  - 本模块 = 同一指标**随时间偏离自身历史基线** (个人 z-score)。

数据来源与 Twin 同源: 读 ``GarminData`` 按 ``device_source_priority`` 逐日逐指标合并
(多源用户每天可能有多行, 一行一个 ``data_source``), 不另写优先级逻辑。

冷启动 / 不确定度:
  - 某指标有效天数 < ``MIN_DAYS_FOR_BASELINE`` (默认 14) → **不产出该指标**
    (别拿 3 天当基线误导)。
  - std 退化 (≈0, 单值序列) → 不算 z (避免除零 / 假性巨大 z)。

异常方向:
  - 双向指标 (HRV / RHR / 睡眠 / 压力 / 电量 / 步数): ``|z| >= Z_DEVIATION_THRESHOLD``
    (默认 2.0) 标 deviation。
  - 单向下限指标 (SpO2 越低越危险, 参考 ``device_source_priority.WORST_VALUE_METRICS``):
    **只标低侧** (z <= -threshold), 高 SpO2 不是异常。
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.device_source_priority import pick_value

logger = logging.getLogger(__name__)

# ── 可配参数 ──────────────────────────────────────────────────────────────
DEFAULT_WINDOW_DAYS = 90
MIN_DAYS_FOR_BASELINE = 14          # 有效天数 < 此 → 不产出该指标 (冷启动)
LOW_CONFIDENCE_DAYS = 30            # 14 <= 有效天数 < 此 → low_confidence
Z_DEVIATION_THRESHOLD = 2.0         # |z| >= 此 → 标 deviation
TREND_RECENT_DAYS = 7               # 趋势: 近 N 天 vs 之前窗口
TREND_REL_DELTA = 0.05             # 近窗均值相对基线均值变化 >= 5% → 标趋势


# ── 指标定义 ──────────────────────────────────────────────────────────────
# (twin_metric_key, GarminData 列名, 中文标签, 单位, low_side_only)
# low_side_only=True: 只标低侧偏离 (越低越危险, e.g. SpO2)。
@dataclass(frozen=True)
class _MetricSpec:
    key: str
    column: str
    label: str
    unit: str
    low_side_only: bool = False


METRIC_SPECS: List[_MetricSpec] = [
    _MetricSpec("hrv", "hrv", "HRV", "ms"),
    _MetricSpec("resting_heart_rate", "resting_heart_rate", "静息心率", "bpm"),
    _MetricSpec("sleep_total", "total_sleep_duration", "总睡眠", "min"),
    _MetricSpec("sleep_deep", "deep_sleep_duration", "深睡", "min"),
    _MetricSpec("stress", "stress_level", "压力", ""),
    _MetricSpec("body_battery", "body_battery_current", "身体电量", ""),
    _MetricSpec("steps", "steps", "步数", ""),
    _MetricSpec("training_load", "acute_load", "急性负荷", ""),
    _MetricSpec("spo2_avg", "spo2_avg", "SpO2", "%", low_side_only=True),
]


@dataclass
class MetricBaseline:
    """单指标个人基线 + 当前偏离结果。"""

    key: str
    label: str
    unit: str
    baseline_mean: float
    baseline_std: float
    n_days: int
    latest: Optional[float] = None
    latest_date: Optional[str] = None
    z: Optional[float] = None
    trend: Optional[str] = None              # "rising" / "falling" / "stable"
    is_deviation: bool = False
    low_confidence: bool = False
    low_side_only: bool = False
    message: Optional[str] = None            # 人话描述 (仅 deviation 时填)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "baseline_mean": round(self.baseline_mean, 2),
            "baseline_std": round(self.baseline_std, 2),
            "n_days": self.n_days,
            "latest": round(self.latest, 2) if self.latest is not None else None,
            "latest_date": self.latest_date,
            "z": round(self.z, 2) if self.z is not None else None,
            "trend": self.trend,
            "is_deviation": self.is_deviation,
            "low_confidence": self.low_confidence,
            "message": self.message,
        }


# ── 纯统计函数 (无 DB, 单测直接喂序列) ─────────────────────────────────────

def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    """样本均值 + 样本标准差 (n<2 → std=0)。"""
    mean = statistics.fmean(values)
    std = statistics.stdev(values) if len(values) >= 2 else 0.0
    return mean, std


def _trend(recent: Sequence[float], baseline_mean: float) -> Optional[str]:
    """近窗均值相对基线的方向。基线≈0 或近窗空 → None。"""
    if not recent or baseline_mean == 0:
        return None
    recent_mean = statistics.fmean(recent)
    rel = (recent_mean - baseline_mean) / abs(baseline_mean)
    if rel >= TREND_REL_DELTA:
        return "rising"
    if rel <= -TREND_REL_DELTA:
        return "falling"
    return "stable"


def compute_metric_baseline(
    spec: _MetricSpec,
    dated_values: Sequence[tuple[date, float]],
    *,
    min_days: int = MIN_DAYS_FOR_BASELINE,
    low_confidence_days: int = LOW_CONFIDENCE_DAYS,
    z_threshold: float = Z_DEVIATION_THRESHOLD,
    recent_days: int = TREND_RECENT_DAYS,
) -> Optional[MetricBaseline]:
    """从 (date, value) 序列算单指标基线/偏离。冷启动不足 → 返回 None。

    纯函数: 不碰 DB。``dated_values`` 应已是单源合并后的逐日值, 任意顺序。
    """
    clean = [(d, float(v)) for d, v in dated_values if v is not None]
    if len(clean) < min_days:
        return None
    clean.sort(key=lambda t: t[0])

    values = [v for _, v in clean]
    mean, std = _mean_std(values)

    latest_date, latest = clean[-1]
    n = len(clean)

    # 近窗趋势: 最近 recent_days 天的值 vs 整体基线
    cutoff = latest_date - timedelta(days=recent_days)
    recent_vals = [v for d, v in clean if d > cutoff]
    trend = _trend(recent_vals, mean)

    # z-score (std 退化 → 不算, 避免除零 / 假性巨大 z)
    z: Optional[float] = None
    is_dev = False
    if std > 1e-9:
        z = (latest - mean) / std
        if spec.low_side_only:
            is_dev = z <= -z_threshold
        else:
            is_dev = abs(z) >= z_threshold

    low_conf = n < low_confidence_days

    mb = MetricBaseline(
        key=spec.key,
        label=spec.label,
        unit=spec.unit,
        baseline_mean=mean,
        baseline_std=std,
        n_days=n,
        latest=latest,
        latest_date=latest_date.isoformat(),
        z=z,
        trend=trend,
        is_deviation=is_dev,
        low_confidence=low_conf,
        low_side_only=spec.low_side_only,
    )
    if is_dev and z is not None:
        mb.message = _deviation_message(mb)
    return mb


def _deviation_message(mb: MetricBaseline) -> str:
    """人话偏离描述, e.g. 'HRV 比你 90 天基线低 1.5σ (58→51ms), ↓ 趋势'。"""
    assert mb.z is not None and mb.latest is not None
    direction = "低" if mb.z < 0 else "高"
    unit = mb.unit
    mean_s = f"{mb.baseline_mean:.0f}{unit}" if unit else f"{mb.baseline_mean:.0f}"
    latest_s = f"{mb.latest:.0f}{unit}" if unit else f"{mb.latest:.0f}"
    trend_arrow = {"rising": " ↑趋势", "falling": " ↓趋势"}.get(mb.trend or "", "")
    conf = " (数据较少, 仅供参考)" if mb.low_confidence else ""
    return (
        f"{mb.label} 比你 {mb.n_days} 天基线{direction} {abs(mb.z):.1f}σ "
        f"({mean_s}→{latest_s}){trend_arrow}{conf}"
    )


# ── DB service (薄层) ──────────────────────────────────────────────────────

def _load_daily_merged(
    db: Session,
    user_id: int,
    columns: Sequence[str],
    window_days: int,
    today: date,
) -> Dict[date, Dict[str, Any]]:
    """读 GarminData 窗口内所有行, 按 (record_date) 分组, 逐指标按设备优先级合并。

    与 Twin 同源: 多源用户每天多行 → ``pick_value`` 选权威值 (SpO2 取最差)。
    user_id 隔离; DB 异常向上抛 (调用方 rollback), 不静默吞。
    """
    from app.models.daily_health import GarminData

    cutoff = today - timedelta(days=window_days)
    rows = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id)
        .filter(GarminData.record_date >= cutoff)
        .filter(GarminData.record_date <= today)
        .all()
    )

    by_date: Dict[date, List[Any]] = {}
    for r in rows:
        by_date.setdefault(r.record_date, []).append(r)

    merged: Dict[date, Dict[str, Any]] = {}
    for d, day_rows in by_date.items():
        day_vals: Dict[str, Any] = {}
        for col in columns:
            v, _src = pick_value(day_rows, col)
            if v is not None:
                day_vals[col] = v
        if day_vals:
            merged[d] = day_vals
    return merged


def compute_personal_baselines(
    db: Session,
    user_id: int,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    today: Optional[date] = None,
    specs: Optional[Sequence[_MetricSpec]] = None,
) -> List[MetricBaseline]:
    """算某 user 的全部指标个人基线。冷启动不足的指标自动跳过。

    返回按"先 deviation 后字母"排序的非空 MetricBaseline 列表。
    DB 异常 → rollback 后重抛 (不假装成功)。
    """
    today = today or date.today()
    specs = list(specs) if specs is not None else METRIC_SPECS
    columns = [s.column for s in specs]

    try:
        merged = _load_daily_merged(db, user_id, columns, window_days, today)
    except Exception:
        db.rollback()
        logger.exception("[personal_baseline] load failed user=%s", user_id)
        raise

    results: List[MetricBaseline] = []
    for spec in specs:
        dated = [
            (d, day[spec.column])
            for d, day in merged.items()
            if spec.column in day
        ]
        mb = compute_metric_baseline(spec, dated)
        if mb is not None:
            results.append(mb)

    results.sort(key=lambda m: (not m.is_deviation, m.key))
    return results
