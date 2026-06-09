"""Per-metric data-source priority — single source of truth for multi-source merge.

After Apple HealthKit ingest, the same (user_id, record_date) can have multiple
``GarminData`` rows, one per ``data_source`` (apple-watch / ringconn / garmin /
oura / withings-app / ...). Any code that wants "the one daily number" for a metric
must decide WHICH source wins. This module is PURE (no DB import) so the policy is
testable in isolation and reused everywhere (twin builder, summary endpoint,
aggregating services).

Priority encodes "for this metric, which device is most accurate":
  - Sleep / SpO2 / HRV / respiration / body temp → smart ring first
    (RingConn 贴肤光路稳,夜间持续监测;Garmin 算法成熟其次;腕表运动位移多再次)
  - Steps / distance / active minutes / active calories / heart rate
    → Apple Watch first (腕上全天佩戴 + 高采样率), Garmin 次之
  - Resting HR / body battery / stress / training readiness/status / VO2max / load
    → Garmin first (这些是 Garmin 专有算法,最权威)

Metrics not in the map fall back to ``DEFAULT_PRIORITY`` (garmin-first, which keeps
legacy single-source garmin users behaving identically). Sources not in any list
are used only as a last resort (any non-null value wins).

Field names here MUST match ``GarminData`` columns (see models/daily_health.py).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

# 设备越靠前优先级越高. 不在列表内的源 = 最低优先级 (last-resort).
_RING_FIRST = ["ringconn", "garmin", "apple-watch", "oura", "withings-app", "unknown"]
_WATCH_FIRST = ["apple-watch", "garmin", "ringconn", "oura", "withings-app", "unknown"]
_GARMIN_FIRST = ["garmin", "apple-watch", "ringconn", "oura", "withings-app", "unknown"]

# 不在 METRIC_SOURCE_PRIORITY 里的指标用这个 (garmin 优先 → 旧单源用户行为不变).
DEFAULT_PRIORITY: List[str] = ["garmin", "apple-watch", "ringconn", "oura", "withings-app", "unknown"]

# 安全下限指标:跨源取"最差"(最小)值,而非按优先级取单源 —— 因为这些是"越低越危险"
# 的单向急性风险阈值,喂给 Safety Guardian(血氧过低规则)。若按优先级取单源,某一源的
# 正常读数会掩盖另一源的危险低值(如戒指 96% 掩盖手表 87% → 87% 本应触发严重低氧告警
# 却被丢弃)。仅对单向下限指标启用;双向指标(如静息心率)不能用 min,仍走优先级。
WORST_VALUE_METRICS = frozenset({"spo2_avg", "spo2_min"})


# 指标 → 设备优先级. 字段名必须与 GarminData 列一致.
METRIC_SOURCE_PRIORITY: Dict[str, List[str]] = {
    # ── 睡眠族 → 戒指优先 ──
    "total_sleep_duration": _RING_FIRST,
    "deep_sleep_duration": _RING_FIRST,
    "rem_sleep_duration": _RING_FIRST,
    "light_sleep_duration": _RING_FIRST,
    "awake_duration": _RING_FIRST,
    "nap_duration": _RING_FIRST,
    "sleep_score": _RING_FIRST,
    # ── 血氧 / HRV → 戒指优先 ──
    "spo2_avg": _RING_FIRST,
    "spo2_min": _RING_FIRST,
    "spo2_max": _RING_FIRST,
    "hrv": _RING_FIRST,
    "hrv_7day_avg": _RING_FIRST,
    # ── 呼吸 → 戒指优先 ──
    "avg_respiration_awake": _RING_FIRST,
    "avg_respiration_sleep": _RING_FIRST,
    "lowest_respiration": _RING_FIRST,
    "highest_respiration": _RING_FIRST,
    "respiratory_rate_min": _RING_FIRST,
    "respiratory_rate_max": _RING_FIRST,
    # ── 体温偏移 → 戒指优先 ──
    "body_temp_deviation_c": _RING_FIRST,
    # ── 活动量 / 心率 → 腕表优先 ──
    "steps": _WATCH_FIRST,
    "distance_meters": _WATCH_FIRST,
    "active_minutes": _WATCH_FIRST,
    "moderate_intensity_minutes": _WATCH_FIRST,
    "vigorous_intensity_minutes": _WATCH_FIRST,
    "active_calories": _WATCH_FIRST,
    "calories_burned": _WATCH_FIRST,
    "bmr_calories": _WATCH_FIRST,
    "floors_climbed": _WATCH_FIRST,
    "avg_heart_rate": _WATCH_FIRST,
    "max_heart_rate": _WATCH_FIRST,
    "min_heart_rate": _WATCH_FIRST,
    # ── Garmin 专有算法 → Garmin 优先 ──
    "resting_heart_rate": _GARMIN_FIRST,
    "body_battery_charged": _GARMIN_FIRST,
    "body_battery_drained": _GARMIN_FIRST,
    "body_battery_most_charged": _GARMIN_FIRST,
    "body_battery_lowest": _GARMIN_FIRST,
    "body_battery_current": _GARMIN_FIRST,
    "stress_level": _GARMIN_FIRST,
    "training_readiness_score": _GARMIN_FIRST,
    "training_readiness_level": _GARMIN_FIRST,
    "training_status": _GARMIN_FIRST,
    "training_status_feedback": _GARMIN_FIRST,
    "vo2max_running": _GARMIN_FIRST,
    "vo2max_cycling": _GARMIN_FIRST,
    "vo2max_fitness_age": _GARMIN_FIRST,
    "acute_load": _GARMIN_FIRST,
    "load_ratio": _GARMIN_FIRST,
    "endurance_score": _GARMIN_FIRST,
    "hill_score": _GARMIN_FIRST,
}


def priority_for(metric: str) -> List[str]:
    """该指标的来源优先级列表 (不在表内 → DEFAULT_PRIORITY)."""
    return METRIC_SOURCE_PRIORITY.get(metric, DEFAULT_PRIORITY)


def _row_source(row: Any) -> str:
    if isinstance(row, dict):
        return row.get("data_source") or "garmin"
    return getattr(row, "data_source", None) or "garmin"


def _row_value(row: Any, metric: str) -> Any:
    if isinstance(row, dict):
        return row.get(metric)
    return getattr(row, metric, None)


def pick_value(rows: Sequence[Any], metric: str) -> tuple[Any, Optional[str]]:
    """单指标按优先级挑值. 返回 (value, winning_source); 全 None → (None, None).

    安全下限指标 (WORST_VALUE_METRICS): 跨源取最小值(最差),不让任一源的正常读数
    掩盖另一源的危险低值。返回该最小值所在的源。
    """
    if metric in WORST_VALUE_METRICS:
        worst_v: Any = None
        worst_src: Optional[str] = None
        for row in rows:
            v = _row_value(row, metric)
            if v is not None and (worst_v is None or v < worst_v):
                worst_v = v
                worst_src = _row_source(row)
        return worst_v, worst_src

    for src in priority_for(metric):
        for row in rows:
            if _row_source(row) == src:
                v = _row_value(row, metric)
                if v is not None:
                    return v, src
    # 优先级表外的源 (含 'unknown' 之外的任意 sourceName) — last resort.
    for row in rows:
        v = _row_value(row, metric)
        if v is not None:
            return v, _row_source(row)
    return None, None


# 默认合并的指标集 (覆盖 GarminData 上所有有 source 分歧意义的数值列).
_DEFAULT_MERGE_METRICS: List[str] = list(METRIC_SOURCE_PRIORITY.keys())


def merge_daily_by_priority(
    rows_for_one_date: Sequence[Any],
    metrics: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """合并同一天跨多源的行,逐指标取最高优先级的非空值.

    入参 ``rows_for_one_date``: 同一 record_date 的若干行 (GarminData ORM 对象或 dict).
    ``metrics``: 要合并的指标集; 缺省合并 METRIC_SOURCE_PRIORITY 全部 key.

    返回一个扁平 dict:
      {<metric>: value, ..., "_source_by_metric": {<metric>: winning_source}}

    单行输入时, merge 结果 == 该行 (back-compat: 旧 garmin-only 用户行为不变).
    """
    keys = list(metrics) if metrics is not None else _DEFAULT_MERGE_METRICS
    out: Dict[str, Any] = {}
    by_metric: Dict[str, str] = {}
    for metric in keys:
        v, src = pick_value(rows_for_one_date, metric)
        if v is not None:
            out[metric] = v
            if src is not None:
                by_metric[metric] = src
    out["_source_by_metric"] = by_metric
    return out
