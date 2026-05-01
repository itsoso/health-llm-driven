"""Nocturnal SpO2 长期趋势聚合 (P-b 分析层).

基于已落盘的 nocturnal_spo2_events + GarminData.total_sleep_duration, 不重跑分析.
这是 H2-6 的 P-b 部分: 采集 (P-a) 已常态运行, 此处补上 longitudinal 视图.

OSAHS 风险 pattern (参考 AASM/ICSD-3 口径, 仅作趋势提示, 不是诊断):
  - ODI ≥ 5 nights% — 频繁氧降
  - min SpO2 < 90% nights% — notable desaturation
  - events in REM% — 典型 OSAHS 模式 (REM 肌张力最低)

不诊断 OSAHS; 仅做模式描述, 由用户/医生解读.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.types import Integer

from app.models.daily_health import GarminData
from app.models.nocturnal_spo2_event import NocturnalSpO2Event

logger = logging.getLogger(__name__)


# ODI 分级 (AASM adult cutoffs)
ODI_MILD = 5.0
ODI_MODERATE = 15.0
ODI_SEVERE = 30.0

# 氧饱和分级
SPO2_HYPOXIA_THRESHOLD = 90.0


@dataclass
class NightSummary:
    night_date: date
    events_count: int
    odi: Optional[float]                 # 事件数/睡眠小时, None 若无 Garmin 睡眠时长
    min_spo2: Optional[float]
    avg_drop_magnitude: Optional[float]
    total_sleep_minutes: Optional[int]
    events_rem_pct: Optional[float]      # REM 期事件比例 0..1
    severity: str                        # normal / mild / moderate / severe


@dataclass
class LongitudinalPattern:
    covered_nights: int              # 有事件表记录的夜数
    nights_with_odi: int             # 其中能算 odi 的
    avg_odi: Optional[float]
    median_min_spo2: Optional[float]
    pct_nights_odi_ge_5: Optional[float]    # 0..1
    pct_nights_min_spo2_below_90: Optional[float]
    pct_events_in_rem: Optional[float]
    mild_nights: int
    moderate_nights: int
    severe_nights: int
    # 文案由前端渲染; 这里只给事实
    pattern_flags: List[str] = field(default_factory=list)


def _severity_from_odi(odi: Optional[float]) -> str:
    if odi is None:
        return "unknown"
    if odi < ODI_MILD:
        return "normal"
    if odi < ODI_MODERATE:
        return "mild"
    if odi < ODI_SEVERE:
        return "moderate"
    return "severe"


def build_longitudinal(
    db: Session, user_id: int, days: int = 30,
) -> Dict[str, Any]:
    """返回近 N 天每夜摘要 + 整体 pattern."""
    end = date.today()
    start = end - timedelta(days=days - 1)

    # 1. 每晚事件聚合 (直接 SQL, 不重跑 analyzer)
    rows = db.query(
        NocturnalSpO2Event.night_date,
        func.count(NocturnalSpO2Event.id).label("events_count"),
        func.min(NocturnalSpO2Event.min_spo2).label("min_spo2"),
        func.avg(NocturnalSpO2Event.drop_magnitude).label("avg_drop"),
        func.sum(
            (NocturnalSpO2Event.sleep_stage == "rem").cast(Integer)
        ).label("rem_events"),
    ).filter(
        NocturnalSpO2Event.user_id == user_id,
        NocturnalSpO2Event.night_date >= start,
        NocturnalSpO2Event.night_date <= end,
    ).group_by(NocturnalSpO2Event.night_date).all()

    events_by_date = {r.night_date: r for r in rows}

    # 2. 睡眠时长 (for ODI)
    garmin_rows = db.query(
        GarminData.record_date, GarminData.total_sleep_duration
    ).filter(
        GarminData.user_id == user_id,
        GarminData.record_date >= start,
        GarminData.record_date <= end,
    ).all()
    sleep_by_date = {r.record_date: r.total_sleep_duration for r in garmin_rows}

    # 3. 组装每晚摘要 (只列有事件或有睡眠的夜)
    nights: List[NightSummary] = []
    d = start
    while d <= end:
        er = events_by_date.get(d)
        total_sleep_min = sleep_by_date.get(d)
        if er is None and total_sleep_min is None:
            d += timedelta(days=1)
            continue

        events_count = int(er.events_count) if er else 0
        min_spo2 = float(er.min_spo2) if er and er.min_spo2 is not None else None
        avg_drop = float(er.avg_drop) if er and er.avg_drop is not None else None
        rem_events = int(er.rem_events or 0) if er else 0
        rem_pct = (rem_events / events_count) if events_count > 0 else None

        odi: Optional[float] = None
        if total_sleep_min and total_sleep_min >= 60:
            sleep_hours = total_sleep_min / 60.0
            odi = round(events_count / sleep_hours, 2)

        nights.append(NightSummary(
            night_date=d,
            events_count=events_count,
            odi=odi,
            min_spo2=min_spo2,
            avg_drop_magnitude=round(avg_drop, 2) if avg_drop is not None else None,
            total_sleep_minutes=total_sleep_min,
            events_rem_pct=round(rem_pct, 3) if rem_pct is not None else None,
            severity=_severity_from_odi(odi),
        ))
        d += timedelta(days=1)

    pattern = _derive_pattern(nights)

    return {
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": days,
        },
        "nights": [_night_to_dict(n) for n in nights],
        "pattern": _pattern_to_dict(pattern),
    }


def _derive_pattern(nights: List[NightSummary]) -> LongitudinalPattern:
    covered = len(nights)
    odi_values = [n.odi for n in nights if n.odi is not None]
    min_spo2_values = [n.min_spo2 for n in nights if n.min_spo2 is not None]

    avg_odi = round(sum(odi_values) / len(odi_values), 2) if odi_values else None
    median_min_spo2 = None
    if min_spo2_values:
        s = sorted(min_spo2_values)
        median_min_spo2 = s[len(s) // 2]

    nights_with_odi = len(odi_values)
    odi_ge_5 = sum(1 for v in odi_values if v >= ODI_MILD)
    spo2_low = sum(1 for v in min_spo2_values if v < SPO2_HYPOXIA_THRESHOLD)

    # REM 事件比例 (所有夜加权)
    total_events = sum(n.events_count for n in nights)
    total_rem_events = sum(
        int(round(n.events_count * (n.events_rem_pct or 0)))
        for n in nights
    )
    pct_rem = (total_rem_events / total_events) if total_events > 0 else None

    mild = sum(1 for n in nights if n.severity == "mild")
    moderate = sum(1 for n in nights if n.severity == "moderate")
    severe = sum(1 for n in nights if n.severity == "severe")

    pct_odi_ge_5 = (odi_ge_5 / nights_with_odi) if nights_with_odi else None
    pct_spo2_low = (spo2_low / len(min_spo2_values)) if min_spo2_values else None

    flags: List[str] = []
    if pct_odi_ge_5 is not None and pct_odi_ge_5 >= 0.50 and nights_with_odi >= 7:
        flags.append("frequent_desaturation")
    if pct_spo2_low is not None and pct_spo2_low >= 0.25 and len(min_spo2_values) >= 7:
        flags.append("notable_hypoxia")
    if pct_rem is not None and pct_rem >= 0.40 and total_events >= 20:
        flags.append("rem_predominant")
    if severe >= 3:
        flags.append("severe_nights_present")

    return LongitudinalPattern(
        covered_nights=covered,
        nights_with_odi=nights_with_odi,
        avg_odi=avg_odi,
        median_min_spo2=median_min_spo2,
        pct_nights_odi_ge_5=round(pct_odi_ge_5, 3) if pct_odi_ge_5 is not None else None,
        pct_nights_min_spo2_below_90=round(pct_spo2_low, 3) if pct_spo2_low is not None else None,
        pct_events_in_rem=round(pct_rem, 3) if pct_rem is not None else None,
        mild_nights=mild,
        moderate_nights=moderate,
        severe_nights=severe,
        pattern_flags=flags,
    )


def _night_to_dict(n: NightSummary) -> Dict[str, Any]:
    return {
        "night_date": n.night_date.isoformat(),
        "events_count": n.events_count,
        "odi": n.odi,
        "min_spo2": n.min_spo2,
        "avg_drop_magnitude": n.avg_drop_magnitude,
        "total_sleep_minutes": n.total_sleep_minutes,
        "events_rem_pct": n.events_rem_pct,
        "severity": n.severity,
    }


def _pattern_to_dict(p: LongitudinalPattern) -> Dict[str, Any]:
    return {
        "covered_nights": p.covered_nights,
        "nights_with_odi": p.nights_with_odi,
        "avg_odi": p.avg_odi,
        "median_min_spo2": p.median_min_spo2,
        "pct_nights_odi_ge_5": p.pct_nights_odi_ge_5,
        "pct_nights_min_spo2_below_90": p.pct_nights_min_spo2_below_90,
        "pct_events_in_rem": p.pct_events_in_rem,
        "mild_nights": p.mild_nights,
        "moderate_nights": p.moderate_nights,
        "severe_nights": p.severe_nights,
        "pattern_flags": p.pattern_flags,
    }
