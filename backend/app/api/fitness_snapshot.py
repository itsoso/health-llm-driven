"""
Fitness Snapshot API (L-fit, 2026-05-06)

给用户一眼看到的"体能快照" — Fitness Age + 周强度分钟进度.

为什么不塞进 dashboard 或 Twin: dashboard 已经拥挤, Twin 是 LLM 上下文; 这两个
metric 是 UI 级 KPI, 用户直接看的数字, 独立端点响应更快.

公式 / 标准:
- Fitness Age = 20 + (peak_vo2 - user_vo2max) / decline_rate
  peak_vo2: male=50, female=42 (ml/kg/min at age 20)
  decline_rate: 0.38 ml/kg/min/year (文献通用)
  结果 clamp 到 [18, 80]
- WHO 强度分钟目标: 150 min/week (moderate + 2x vigorous)
  Garmin 自动把 vigorous 乘 2 算进 total intensity minutes.
"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData
from app.api.auth import get_current_user_required

router = APIRouter()


class FitnessSnapshot(BaseModel):
    vo2max: Optional[float] = None
    vo2max_source: Optional[str] = None  # running / cycling
    chronological_age: Optional[int] = None
    fitness_age: Optional[int] = None
    age_delta: Optional[int] = None      # fitness_age - chronological_age. 负数 = 年轻

    # 强度分钟 (本周)
    intensity_this_week: int = 0         # total = moderate + 2 * vigorous
    intensity_goal: int = 150
    intensity_pct: float = 0.0
    moderate_this_week: int = 0
    vigorous_this_week: int = 0
    days_tracked_this_week: int = 0

    # 元信息
    last_data_date: Optional[str] = None


def _compute_fitness_age(vo2max: float, gender: Optional[str]) -> int:
    """Return estimated fitness age from VO2max.

    NTNU/Norwegian-style simplification: 按 20 岁基线 + 每年 0.38 ml/kg/min 衰减反推.
    """
    peak = 50.0 if (gender or "").lower() in ("male", "m", "男") else 42.0
    decline = 0.38
    age_f = 20.0 + (peak - float(vo2max)) / decline
    return int(round(max(18.0, min(80.0, age_f))))


@router.get("/me", response_model=FitnessSnapshot)
def get_my_fitness_snapshot(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> FitnessSnapshot:
    """返回当前用户的体能快照 (Fitness Age + 周强度进度)."""
    today = date.today()
    # 本周 = Monday-Sunday
    monday = today - timedelta(days=today.weekday())

    # 近 7 天的 Garmin 数据 (VO2max 取最新, 强度分钟求和)
    rows = (
        db.query(GarminData)
        .filter(GarminData.user_id == current_user.id)
        .filter(GarminData.record_date >= monday)
        .order_by(GarminData.record_date.desc())
        .all()
    )

    # VO2max — 取最新不为空的
    vo2max: Optional[float] = None
    vo2max_source: Optional[str] = None
    last_date: Optional[date] = None

    # 如本周没有, 回溯 60 天内最新一条
    if rows and rows[0].vo2max_running:
        vo2max = float(rows[0].vo2max_running)
        vo2max_source = "running"
        last_date = rows[0].record_date
    elif rows and rows[0].vo2max_cycling:
        vo2max = float(rows[0].vo2max_cycling)
        vo2max_source = "cycling"
        last_date = rows[0].record_date
    else:
        fallback = (
            db.query(GarminData)
            .filter(GarminData.user_id == current_user.id)
            .filter(GarminData.record_date >= today - timedelta(days=60))
            .filter(
                (GarminData.vo2max_running.isnot(None))
                | (GarminData.vo2max_cycling.isnot(None))
            )
            .order_by(GarminData.record_date.desc())
            .first()
        )
        if fallback:
            if fallback.vo2max_running:
                vo2max = float(fallback.vo2max_running)
                vo2max_source = "running"
            elif fallback.vo2max_cycling:
                vo2max = float(fallback.vo2max_cycling)
                vo2max_source = "cycling"
            last_date = fallback.record_date

    # 年龄 + 性别 — 从 profile 取
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == current_user.id)
        .first()
    )
    chron_age = profile.age if profile else None
    gender = profile.gender if profile else None

    fitness_age: Optional[int] = None
    age_delta: Optional[int] = None
    if vo2max and chron_age:
        fitness_age = _compute_fitness_age(vo2max, gender)
        age_delta = fitness_age - chron_age

    # 强度分钟本周累计
    moderate = sum((r.moderate_intensity_minutes or 0) for r in rows)
    vigorous = sum((r.vigorous_intensity_minutes or 0) for r in rows)
    total = moderate + 2 * vigorous  # WHO 规则: vigorous 算 2 倍

    goal = int(rows[0].intensity_minutes_goal) if (rows and rows[0].intensity_minutes_goal) else 150
    pct = min(100.0, (total / goal) * 100.0) if goal else 0.0
    days_tracked = sum(
        1 for r in rows
        if (r.moderate_intensity_minutes is not None or r.vigorous_intensity_minutes is not None)
    )

    return FitnessSnapshot(
        vo2max=vo2max,
        vo2max_source=vo2max_source,
        chronological_age=chron_age,
        fitness_age=fitness_age,
        age_delta=age_delta,
        intensity_this_week=total,
        intensity_goal=goal,
        intensity_pct=round(pct, 1),
        moderate_this_week=moderate,
        vigorous_this_week=vigorous,
        days_tracked_this_week=days_tracked,
        last_data_date=last_date.isoformat() if last_date else None,
    )
