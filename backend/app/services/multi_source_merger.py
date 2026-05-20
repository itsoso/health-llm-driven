"""
Multi-source field merger for GarminData rows.

After Apple HealthKit ingest, the same (user_id, record_date) can have multiple
GarminData rows — one per data_source (apple-watch / ringconn / oura / garmin / ...).
The integration service used to pick `latest by date` and miss fields that only
exist in another source row.

Priority lists encode "for this field, which source is most accurate":
  - Heart-rate family (HR / HRV / RHR / SpO2): smart rings > apple-watch > garmin
    (戒指贴肤,光路稳;腕表运动时位移多;Garmin 算法老)
  - Steps / calories / distance: garmin > apple-watch (Garmin 户外 GPS 训练专精)
  - Sleep: oura > apple-watch > garmin (Oura 临床贴近,Watch 缺夜间贴肤,Garmin 三流)
  - Body temp deviation: oura > apple-watch (戒指夜间持续监测,Watch 散点)
  - Stress / body_battery: garmin only (专有算法)

未在白名单内的源 fallback 到 'garmin' 等价优先级 (历史兼容)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


# 优先级越靠前越优. 不在表内的源按"未知"处理 (放最后).
_PRIORITY_HR_FAMILY = ["ringconn", "oura", "apple-watch", "garmin", "withings-app"]
_PRIORITY_STEPS_CAL = ["garmin", "apple-watch", "ringconn", "oura"]
_PRIORITY_SLEEP = ["oura", "ringconn", "apple-watch", "garmin"]
_PRIORITY_BODY_TEMP = ["oura", "apple-watch", "ringconn"]
_PRIORITY_DEFAULT = ["garmin", "apple-watch", "ringconn", "oura", "withings-app", "garmin-app"]


# 字段 → 优先级列表. 未列出的字段按 _PRIORITY_DEFAULT.
_FIELD_PRIORITY: Dict[str, List[str]] = {
    # HR 家族 — 戒指 > 表 > Garmin
    "hrv": _PRIORITY_HR_FAMILY,
    "resting_heart_rate": _PRIORITY_HR_FAMILY,
    "max_heart_rate": _PRIORITY_HR_FAMILY,
    "avg_heart_rate": _PRIORITY_HR_FAMILY,
    "spo2_avg": _PRIORITY_HR_FAMILY,
    "spo2_min": _PRIORITY_HR_FAMILY,
    # 训练 — Garmin 优先
    "steps": _PRIORITY_STEPS_CAL,
    "calories_burned": _PRIORITY_STEPS_CAL,
    "active_calories": _PRIORITY_STEPS_CAL,
    "basal_calories": _PRIORITY_STEPS_CAL,
    "distance_km": _PRIORITY_STEPS_CAL,
    # 睡眠 — Oura 优先
    "sleep_score": _PRIORITY_SLEEP,
    "sleep_hours": _PRIORITY_SLEEP,
    "deep_sleep_hours": _PRIORITY_SLEEP,
    "rem_sleep_hours": _PRIORITY_SLEEP,
    # 体温
    "body_temp_deviation_c": _PRIORITY_BODY_TEMP,
    # 呼吸
    "respiratory_rate_min": _PRIORITY_HR_FAMILY,
    "respiratory_rate_max": _PRIORITY_HR_FAMILY,
}


def _row_source(row: Any) -> str:
    return getattr(row, "data_source", None) or "garmin"


def _row_value(row: Any, field: str) -> Any:
    return getattr(row, field, None)


def _priority_for(field: str) -> List[str]:
    return _FIELD_PRIORITY.get(field, _PRIORITY_DEFAULT)


def merge_field(rows: Sequence[Any], field: str) -> tuple[Any, Optional[str]]:
    """对单个字段按优先级挑值. 返回 (value, winning_source) — 都 None 则两个 None."""
    priority = _priority_for(field)
    # 按 priority 顺序找第一个有值的 row
    for src in priority:
        for row in rows:
            if _row_source(row) == src:
                v = _row_value(row, field)
                if v is not None:
                    return v, src
    # priority 外的源 (含 'unknown') 兜底:任何 non-None 即返回
    for row in rows:
        v = _row_value(row, field)
        if v is not None:
            return v, _row_source(row)
    return None, None


def merge_rows(rows: Sequence[Any], fields: Sequence[str]) -> Dict[str, Any]:
    """
    对多行 GarminData 同 (user, date) 按字段独立 source 优先级合成.

    返回:
      {
        "values": {field: value},
        "sources": {field: data_source},  # 哪个源中标
      }
    """
    out_vals: Dict[str, Any] = {}
    out_srcs: Dict[str, str] = {}
    for field in fields:
        v, s = merge_field(rows, field)
        out_vals[field] = v
        if s is not None:
            out_srcs[field] = s
    return {"values": out_vals, "sources": out_srcs}
