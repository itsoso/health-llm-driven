"""C1 周健身计划 + C2 动作图文指导 —— /api/v1/fitness。

C1(周计划):GET 取/生成本周提议 → POST confirm(T2 确认+排程) / dismiss。
C2(动作指导):确定性策展数据集的浏览列表 + 详情(非 LLM,见 services/exercise_guide.py)。

安全:user_id 一律取自 token(IDOR);文案全程 hedge,不出处方剂量 / 医疗裁决;
引用指标处标「相关非因果」;disclaimer/safety_note 带「伤病先就医 + 非医疗建议」。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services import exercise_guide, fitness_plan_service

router = APIRouter(prefix="/fitness", tags=["fitness"])


# ───────────────────────── C1 response models ─────────────────────────


class WorkoutOut(BaseModel):
    name: str
    exercise_key: str
    duration_min: int
    intensity_note: str


class DayOut(BaseModel):
    date: str
    weekday: str
    day_type: str  # hard / easy / rest
    workout: Optional[WorkoutOut] = None
    rationale: str


class WeeklyPlanOut(BaseModel):
    plan_id: Optional[int] = None
    status: Optional[str] = None  # proposed / confirmed / null
    week_start: str
    goal: str
    acwr: Optional[float] = None
    readiness_note: str
    days: List[DayOut]
    disclaimer: str


class ConfirmIn(BaseModel):
    plan_id: int


class ConfirmOut(BaseModel):
    confirmed: bool
    plan_id: int
    scheduled_count: int


class DismissOut(BaseModel):
    dismissed: bool


# ───────────────────────── C2 response models ─────────────────────────


class ExerciseListItem(BaseModel):
    exercise_key: str
    name: str


class ExerciseListOut(BaseModel):
    exercises: List[ExerciseListItem]


class ExerciseDetailOut(BaseModel):
    exercise_key: str
    name: str
    steps: List[str]
    common_mistakes: List[str]
    injury_red_lines: List[str]
    safety_note: str


# ───────────────────────── C1 endpoints ─────────────────────────


@router.get("/weekly-plan", response_model=WeeklyPlanOut)
def get_weekly_plan(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """本周已有计划则返回,否则从 twin 生成新提议(status=proposed)。"""
    return fitness_plan_service.get_or_generate_weekly_plan(db, current_user.id)


@router.post("/weekly-plan/confirm", response_model=ConfirmOut)
def confirm_weekly_plan(
    body: ConfirmIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """T2 一键确认 → 排程(幂等:确认两次不重复排程)。"""
    try:
        return fitness_plan_service.confirm_weekly_plan(db, current_user.id, body.plan_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="计划不存在")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/weekly-plan/dismiss", response_model=DismissOut)
def dismiss_weekly_plan(
    body: ConfirmIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        return fitness_plan_service.dismiss_weekly_plan(db, current_user.id, body.plan_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="计划不存在")


# ───────────────────────── C2 endpoints ─────────────────────────


@router.get("/exercise-guide", response_model=ExerciseListOut)
def list_exercise_guide():
    """浏览动作图文指导列表(key + name)。"""
    return {"exercises": exercise_guide.list_exercises()}


@router.get("/exercise-guide/{exercise_key}", response_model=ExerciseDetailOut)
def get_exercise_guide_detail(exercise_key: str):
    """单个动作完整图文条目;未知 key → 404。"""
    entry = exercise_guide.get_exercise(exercise_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="动作不存在")
    return entry
