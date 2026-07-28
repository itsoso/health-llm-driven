"""Run Episode Parser — 把 WorkoutRecord + Twin 快照转成 Episode 触发 context.

这里是 Rule Engine 的一部分 (零 LLM). 只做:
1. 标准化跑步指标 (distance_km, duration_min, avg_hr, pace_sec_per_km)
2. 建 context_snapshot (天气/aqi/睡眠/HRV/ACWR)
3. 建 baseline_snapshot (7d avg HR, pace, 30d sleep median)

ACWR 复用 HealthTwin 的训练负荷服务和可靠性边界，避免 Episode 与安全规则口径漂移。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.daily_health import WorkoutRecord, GarminData
from app.services.exercise_recovery_service import ExerciseRecoveryService
from app.utils.timezone import get_user_timezone

logger = logging.getLogger(__name__)


@dataclass
class RunEpisodeInput:
    workout: WorkoutRecord
    context: Dict[str, Any]
    baseline: Dict[str, Any]
    occurred_at: datetime


def parse_run_episode(
    db: Session,
    user_id: int,
    workout: WorkoutRecord,
    weather: Optional[Dict[str, Any]] = None,
) -> RunEpisodeInput:
    """构建跑步 Episode 的触发输入 — context + baseline snapshot."""
    occurred_at = workout.end_time or workout.start_time or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(
            tzinfo=get_user_timezone(db, user_id),
        ).astimezone(timezone.utc)

    distance_km = (workout.distance_meters or 0) / 1000.0
    duration_min = (workout.duration_seconds or 0) / 60.0

    context: Dict[str, Any] = {
        "distance_km": round(distance_km, 2),
        "duration_min": round(duration_min, 1),
        "avg_hr": workout.avg_heart_rate,
        "max_hr": workout.max_heart_rate,
        "pace_sec_per_km": workout.avg_pace_seconds_per_km,
        "training_effect_aerobic": workout.training_effect_aerobic,
        "training_load": workout.training_load,
        "perceived_exertion": workout.perceived_exertion,
        "feeling": workout.feeling,
        "symptoms": [],  # 初始为空, feedback 回来时填
    }

    # 天气 — 注入快照
    if weather:
        context["weather"] = weather

    # 睡眠前一晚 — 查最近的 GarminData
    prior_date = workout.workout_date or occurred_at.date()
    gd = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id, GarminData.record_date <= prior_date)
        .order_by(GarminData.record_date.desc())
        .first()
    )
    if gd and gd.total_sleep_duration:
        context["sleep_prior_h"] = round(gd.total_sleep_duration / 60.0, 2)
    if gd:
        context["hrv_latest"] = getattr(gd, "hrv_last_night_avg", None)
        context["body_battery_current"] = getattr(gd, "body_battery_current", None)

    # ACWR 7/28d training load ratio
    acwr = _compute_acwr(db, user_id, workout.workout_date)
    if acwr is not None:
        context["acwr"] = acwr

    # Baseline — 7d avg HR / pace, 30d sleep median
    baseline = _compute_baseline(db, user_id, occurred_at)

    return RunEpisodeInput(
        workout=workout,
        context=context,
        baseline=baseline,
        occurred_at=occurred_at,
    )


def _compute_acwr(db: Session, user_id: int, as_of_date: date) -> Optional[float]:
    """Return the same reliable ACWR value used by HealthTwin and Safety."""

    result = ExerciseRecoveryService().get_training_load(
        db,
        user_id,
        as_of_date=as_of_date,
    )
    return result.get("acwr")


def _compute_baseline(db: Session, user_id: int, now: datetime) -> Dict[str, Any]:
    """7d 训练均值 + 30d 睡眠中位数."""
    out: Dict[str, Any] = {}

    # 7d workout 均 HR / pace
    rows = (
        db.query(WorkoutRecord)
        .filter(
            and_(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.end_time >= now - timedelta(days=7),
                WorkoutRecord.end_time <= now,
                WorkoutRecord.workout_type == "running",
            )
        )
        .all()
    )
    hrs = [r.avg_heart_rate for r in rows if r.avg_heart_rate]
    if hrs:
        out["avg_hr_7d"] = int(sum(hrs) / len(hrs))
    paces = [r.avg_pace_seconds_per_km for r in rows if r.avg_pace_seconds_per_km]
    if paces:
        out["avg_pace_sec_7d"] = int(sum(paces) / len(paces))

    # 30d sleep median
    gd_rows = (
        db.query(GarminData)
        .filter(
            and_(
                GarminData.user_id == user_id,
                GarminData.record_date >= (now - timedelta(days=30)).date(),
            )
        )
        .all()
    )
    sleeps = sorted(
        r.total_sleep_duration / 60.0
        for r in gd_rows
        if r.total_sleep_duration
    )
    if sleeps:
        mid = len(sleeps) // 2
        out["sleep_median_h_30d"] = round(sleeps[mid], 2)

    return out
