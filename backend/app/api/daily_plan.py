"""Daily Operating Plan API."""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.intervention_event import InterventionEvent
from app.models.user import User
from app.services.daily_operating_plan import build_daily_operating_plan

router = APIRouter(prefix="/daily-plan", tags=["daily-plan"])


class DailyPlanActionFeedbackRequest(BaseModel):
    status: Literal["accepted", "adjusted", "done", "skipped", "failed"]
    reason: Optional[str] = Field(default=None, max_length=500)
    plan_date: Optional[date] = Field(default=None, description="默认今天")


class DailyPlanActionFeedbackResponse(BaseModel):
    id: int
    plan_id: Optional[int]
    plan_date: date
    action_key: str
    action_title: str
    status: str
    reason: Optional[str]
    source: str


@router.get("/me")
def get_my_daily_plan(
    plan_date: Optional[date] = Query(None, description="默认今天"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户当天操作计划."""
    return build_daily_operating_plan(db, current_user.id, plan_date=plan_date)


@router.post("/me/actions/{action_key}/feedback", response_model=DailyPlanActionFeedbackResponse)
def submit_my_daily_plan_action_feedback(
    action_key: str,
    request: DailyPlanActionFeedbackRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """记录 Daily Plan 行动反馈.

    这是 append-only learning event, 不修改当天计划快照本身。
    """
    payload = build_daily_operating_plan(db, current_user.id, plan_date=request.plan_date)
    actions = payload.get("actions") if isinstance(payload, dict) else []
    action = next(
        (
            a for a in actions
            if isinstance(a, dict) and str(a.get("action_key") or "") == action_key
        ),
        None,
    )
    if not action:
        raise HTTPException(status_code=404, detail="Daily Plan action 不存在")

    plan_date = date.fromisoformat(payload["plan_date"]) if isinstance(payload.get("plan_date"), str) else payload["plan_date"]
    row = InterventionEvent(
        user_id=current_user.id,
        plan_id=payload.get("id"),
        plan_date=plan_date,
        action_key=action_key,
        action_domain=action.get("domain"),
        action_title=str(action.get("title") or action_key),
        feedback_status=request.status,
        reason=request.reason,
        source="daily_plan",
        action_snapshot=action,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return DailyPlanActionFeedbackResponse(
        id=row.id,
        plan_id=row.plan_id,
        plan_date=row.plan_date,
        action_key=row.action_key,
        action_title=row.action_title,
        status=row.feedback_status,
        reason=row.reason,
        source=row.source,
    )
