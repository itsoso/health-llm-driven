# -*- coding: utf-8 -*-
"""Compact health context summaries for LLM prompts.

The agent should receive aggregate state and decision boundaries, not raw
wearable rows. This module keeps the 7-day wearable summary deterministic so it
can be reused by system prompts and post-record dynamic cards.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import desc as sa_desc
from sqlalchemy.orm import Session

from app.models.daily_health import GarminData
from app.services.multi_source_merger import merge_rows


_SUMMARY_FIELDS = [
    "total_sleep_duration",
    "sleep_score",
    "hrv",
    "resting_heart_rate",
    "steps",
    "active_minutes",
    "body_battery_current",
    "stress_level",
]

_PRIVACY_BOUNDARY = (
    "仅向 LLM 注入最近7日聚合摘要、状态标签和建议偏置；不注入原始逐日记录、"
    "分钟级心率、睡眠阶段明细或设备原始 payload。"
)


def build_wearable_context_summary(
    db: Session,
    user_id: Optional[int],
    *,
    days: int = 7,
    as_of: Optional[date] = None,
) -> dict[str, Any]:
    """Return a compact 7-day wearable summary.

    Shape intentionally excludes raw daily rows. Callers can format this for a
    prompt or read ``meal_guidance_context`` for deterministic UI guidance.
    """
    window_days = max(int(days or 7), 1)
    today = as_of or date.today()
    since = today - timedelta(days=window_days - 1)

    base: dict[str, Any] = {
        "window_days": window_days,
        "date_range": {"start": since.isoformat(), "end": today.isoformat()},
        "privacy_boundary": _PRIVACY_BOUNDARY,
    }
    if user_id is None:
        return _data_gap(base, "missing_user_id")

    rows = (
        db.query(GarminData)
        .filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= since,
            GarminData.record_date <= today,
        )
        .order_by(sa_desc(GarminData.record_date), sa_desc(GarminData.id))
        .all()
    )
    if not rows:
        return _data_gap(base, "wearable_data_missing")

    merged_by_date: dict[date, dict[str, Any]] = {}
    grouped: dict[date, list[GarminData]] = {}
    sources: set[str] = set()
    for row in rows:
        grouped.setdefault(row.record_date, []).append(row)
        if row.data_source:
            sources.add(row.data_source)

    for record_date, day_rows in grouped.items():
        merged = merge_rows(day_rows, _SUMMARY_FIELDS)
        merged_by_date[record_date] = merged["values"]
        sources.update(str(src) for src in merged["sources"].values() if src)

    dates = sorted(merged_by_date.keys())
    latest_values = merged_by_date[dates[-1]]

    sleep_minutes = _values(merged_by_date, "total_sleep_duration")
    sleep_scores = _values(merged_by_date, "sleep_score")
    hrv_values = _values(merged_by_date, "hrv")
    rhr_values = _values(merged_by_date, "resting_heart_rate")
    step_values = _values(merged_by_date, "steps")
    active_minutes = _values(merged_by_date, "active_minutes")
    battery_values = _values(merged_by_date, "body_battery_current")
    stress_values = _values(merged_by_date, "stress_level")

    sleep_avg_h = _round(_avg(sleep_minutes) / 60 if sleep_minutes else None, 1)
    sleep_latest_h = _round(_num(latest_values.get("total_sleep_duration")) / 60 if latest_values.get("total_sleep_duration") is not None else None, 1)
    sleep_status = _sleep_status(sleep_avg_h, _avg(sleep_scores), sleep_latest_h)

    hrv_avg = _round(_avg(hrv_values), 1)
    hrv_latest = _round(_num(latest_values.get("hrv")), 1)
    hrv_status = _hrv_status(hrv_latest, hrv_avg)

    rhr_avg = _round(_avg(rhr_values), 1)
    rhr_latest = _round(_num(latest_values.get("resting_heart_rate")), 1)
    rhr_status = _rhr_status(rhr_latest, rhr_avg)

    avg_steps = _round(_avg(step_values), 0)
    latest_steps = _round(_num(latest_values.get("steps")), 0)
    activity_status = _activity_status(avg_steps)

    avg_battery = _round(_avg(battery_values), 0)
    avg_stress = _round(_avg(stress_values), 0)
    recovery_state, meal_biases, meal_summary = _meal_guidance_context(
        sleep_status=sleep_status,
        hrv_status=hrv_status,
        rhr_status=rhr_status,
        activity_status=activity_status,
        avg_battery=avg_battery,
        avg_stress=avg_stress,
    )

    return {
        **base,
        "status": "present",
        "data_gap": False,
        "sources": sorted(sources),
        "coverage": {
            "days_with_data": len(dates),
            "sleep_days": len(sleep_minutes),
            "hrv_days": len(hrv_values),
            "rhr_days": len(rhr_values),
            "activity_days": len(step_values),
        },
        "metrics": {
            "sleep": {
                "status": sleep_status,
                "avg_hours": sleep_avg_h,
                "latest_hours": sleep_latest_h,
                "avg_score": _round(_avg(sleep_scores), 0),
            },
            "hrv": {
                "status": hrv_status,
                "avg_ms": hrv_avg,
                "latest_ms": hrv_latest,
            },
            "resting_heart_rate": {
                "status": rhr_status,
                "avg_bpm": rhr_avg,
                "latest_bpm": rhr_latest,
            },
            "activity": {
                "status": activity_status,
                "avg_steps": avg_steps,
                "latest_steps": latest_steps,
                "avg_active_minutes": _round(_avg(active_minutes), 0),
            },
            "body_battery": {
                "avg": avg_battery,
                "status": _battery_status(avg_battery),
            },
            "stress": {
                "avg": avg_stress,
                "status": _stress_status(avg_stress),
            },
        },
        "meal_guidance_context": {
            "recovery_state": recovery_state,
            "meal_advice_bias": meal_biases,
            "summary": meal_summary,
        },
    }


def format_wearable_context_summary_for_prompt(summary: dict[str, Any]) -> str:
    """Render the structured summary as a compact prompt section."""
    window_days = int(summary.get("window_days") or 7)
    if summary.get("status") == "data_gap":
        reason = summary.get("reason") or "wearable_data_missing"
        return "\n".join(
            [
                "[可穿戴7日摘要]",
                f"状态: data_gap ({reason}); 最近{window_days}天缺少可穿戴 sleep/HRV/RHR/activity 聚合数据。",
                "饮食建议约束: 不根据未同步的恢复状态做强个性化; 可提示用户同步设备授权。",
                f"隐私边界: {summary.get('privacy_boundary') or _PRIVACY_BOUNDARY}",
            ]
        )

    metrics = summary.get("metrics") or {}
    meal_context = summary.get("meal_guidance_context") or {}
    sources = ", ".join(summary.get("sources") or []) or "unknown"
    sleep = metrics.get("sleep") or {}
    hrv = metrics.get("hrv") or {}
    rhr = metrics.get("resting_heart_rate") or {}
    activity = metrics.get("activity") or {}
    battery = metrics.get("body_battery") or {}
    stress = metrics.get("stress") or {}

    return "\n".join(
        [
            "[可穿戴7日摘要]",
            f"窗口: 最近{window_days}天; 数据源: {sources}",
            f"恢复态: {meal_context.get('recovery_state', 'unknown')}; 饮食偏置: {', '.join(meal_context.get('meal_advice_bias') or [])}",
            (
                f"睡眠: {sleep.get('status', 'data_gap')} "
                f"(均值{_display(sleep.get('avg_hours'))}h, 最新{_display(sleep.get('latest_hours'))}h, "
                f"评分{_display(sleep.get('avg_score'))})"
            ),
            f"HRV: {hrv.get('status', 'data_gap')} (均值{_display(hrv.get('avg_ms'))}ms, 最新{_display(hrv.get('latest_ms'))}ms)",
            f"静息心率: {rhr.get('status', 'data_gap')} (均值{_display(rhr.get('avg_bpm'))}bpm, 最新{_display(rhr.get('latest_bpm'))}bpm)",
            (
                f"活动: {activity.get('status', 'data_gap')} "
                f"(均步{_display(activity.get('avg_steps'))}, 活动{_display(activity.get('avg_active_minutes'))}min)"
            ),
            f"身体电量/压力: {battery.get('status', 'data_gap')} / {stress.get('status', 'data_gap')}",
            f"饮食建议解释: {meal_context.get('summary', '数据不足')}",
            f"隐私边界: {summary.get('privacy_boundary') or _PRIVACY_BOUNDARY}",
        ]
    )


def _data_gap(base: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **base,
        "status": "data_gap",
        "data_gap": True,
        "reason": reason,
        "sources": [],
        "metrics": {},
        "meal_guidance_context": {
            "recovery_state": "unknown",
            "meal_advice_bias": ["avoid_over_personalization_without_wearable_data"],
            "summary": "缺少最近 7 天可穿戴恢复数据，饮食建议只能按通用目标给出。",
        },
    }


def _values(rows_by_date: dict[date, dict[str, Any]], field: str) -> list[float]:
    values: list[float] = []
    for values_for_day in rows_by_date.values():
        num = _num(values_for_day.get(field))
        if num is not None:
            values.append(num)
    return values


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _avg(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _round(value: Optional[float], digits: int) -> Optional[float]:
    if value is None:
        return None
    rounded = round(float(value), digits)
    if digits == 0:
        return int(rounded)
    return rounded


def _display(value: Any) -> str:
    if value is None:
        return "无"
    return str(value)


def _sleep_status(avg_hours: Optional[float], avg_score: Optional[float], latest_hours: Optional[float]) -> str:
    if avg_hours is None and avg_score is None and latest_hours is None:
        return "data_gap"
    if (avg_hours is not None and avg_hours < 6) or (latest_hours is not None and latest_hours < 6) or (avg_score is not None and avg_score < 65):
        return "poor"
    if (avg_hours is not None and avg_hours >= 7) and (avg_score is None or avg_score >= 75):
        return "good"
    return "mixed"


def _hrv_status(latest_ms: Optional[float], avg_ms: Optional[float]) -> str:
    if latest_ms is None and avg_ms is None:
        return "data_gap"
    value = latest_ms if latest_ms is not None else avg_ms
    if value is None:
        return "data_gap"
    if value < 40:
        return "low"
    if avg_ms and latest_ms and latest_ms < avg_ms * 0.9:
        return "low"
    if value >= 55:
        return "normal"
    return "mixed"


def _rhr_status(latest_bpm: Optional[float], avg_bpm: Optional[float]) -> str:
    if latest_bpm is None and avg_bpm is None:
        return "data_gap"
    value = latest_bpm if latest_bpm is not None else avg_bpm
    if value is None:
        return "data_gap"
    if value >= 70:
        return "elevated"
    if avg_bpm and latest_bpm and latest_bpm >= avg_bpm + 5:
        return "elevated"
    return "normal"


def _activity_status(avg_steps: Optional[float]) -> str:
    if avg_steps is None:
        return "data_gap"
    if avg_steps < 4000:
        return "low"
    if avg_steps >= 7500:
        return "active"
    return "moderate"


def _battery_status(avg_battery: Optional[float]) -> str:
    if avg_battery is None:
        return "data_gap"
    if avg_battery < 35:
        return "low"
    if avg_battery >= 65:
        return "good"
    return "moderate"


def _stress_status(avg_stress: Optional[float]) -> str:
    if avg_stress is None:
        return "data_gap"
    if avg_stress >= 65:
        return "high"
    if avg_stress <= 40:
        return "low"
    return "moderate"


def _meal_guidance_context(
    *,
    sleep_status: str,
    hrv_status: str,
    rhr_status: str,
    activity_status: str,
    avg_battery: Optional[float],
    avg_stress: Optional[float],
) -> tuple[str, list[str], str]:
    strained = (
        sleep_status == "poor"
        or hrv_status == "low"
        or rhr_status == "elevated"
        or (avg_battery is not None and avg_battery < 35)
        or (avg_stress is not None and avg_stress >= 65)
    )
    recovered = (
        sleep_status == "good"
        and hrv_status in {"normal", "mixed"}
        and rhr_status == "normal"
        and (avg_battery is None or avg_battery >= 60)
        and (avg_stress is None or avg_stress <= 45)
    )
    if strained:
        return (
            "strained",
            [
                "gentle_digestible_meal",
                "avoid_large_calorie_deficit",
                "prioritize_hydration",
                "avoid_late_caffeine_alcohol",
            ],
            "最近睡眠/HRV/静息心率/压力提示恢复偏紧，下一餐应温和、足蛋白、不过度制造热量缺口。",
        )
    if recovered:
        return (
            "recovered",
            [
                "normal_protein_target",
                "fiber_and_training_support",
                "keep_energy_balanced",
            ],
            "最近恢复状态较好，下一餐可按正常蛋白和蔬菜目标推进，避免过度节食。",
        )
    return (
        "neutral",
        ["balanced_meal", "avoid_extreme_adjustment"],
        "恢复状态信号中性，下一餐按均衡结构和当天缺口微调。",
    )
