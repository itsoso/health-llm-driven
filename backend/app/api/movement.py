"""运动执行层 API (R17 任务线 / JITAI)。

GET /api/v1/movement/guided-task —— readiness 门控的引导式运动任务。
内容走循证库(exercise_library),门控走 recovery_decision;LLM 不参与裁决。
强制 user_id 隔离(get_current_user_required)。
"""
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.movement.guided_task import build_guided_task

router = APIRouter(prefix="/movement", tags=["运动执行层"])


class GateOut(BaseModel):
    decision: Literal["do", "modified", "rest_instead"]
    readiness_zone: Literal["green", "yellow", "red", "unknown"]
    reason: str


class ExerciseOut(BaseModel):
    id: str
    name: str
    evidence_tier: str
    cues: List[str]
    media_ref: Optional[str] = None
    contraindications: List[str]


class PlanOut(BaseModel):
    sets: Optional[int] = None
    reps: Optional[int] = None
    duration_sec: Optional[int] = None
    rest_sec: Optional[int] = None
    progression_note: str


class CaptureOut(BaseModel):
    mode: Literal["manual"]
    fields: List[str]


class GuidedTaskOut(BaseModel):
    domain: str
    gate: GateOut
    title: str
    exercise: ExerciseOut
    plan: PlanOut
    voice_script: List[str]
    capture: CaptureOut
    safety_note: Optional[str] = None


@router.get(
    "/guided-task",
    response_model=GuidedTaskOut,
    summary="readiness 门控的引导式运动任务(RED 不推力量改拉伸)",
)
async def get_guided_task(
    domain: Literal["strength", "mobility"] = Query("strength"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """到点的引导式运动任务 —— 经 recovery_decision 门控后装配。

    - RED + strength → rest_instead,换基础拉伸
    - YELLOW → modified(减量)
    - GREEN → do(按上次完成确定性进阶)
    动作要领 / 语音来自循证内容库,非 LLM 现编。
    """
    return build_guided_task(db, current_user.id, domain)
