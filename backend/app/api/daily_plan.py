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
from app.schemas.daily_plan_feedback import (
    DailyPlanActionEventRequest,
    DailyPlanActionEventResponse,
)
from app.services.daily_operating_plan import build_daily_operating_plan
from app.services.health_operating_review import (
    SUPPORTED_REVIEW_WINDOWS,
    build_health_operating_review,
)

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


def _daily_plan_date(payload: dict) -> date:
    raw_plan_date = payload.get("plan_date")
    if isinstance(raw_plan_date, str):
        return date.fromisoformat(raw_plan_date)
    return raw_plan_date


def _load_daily_plan_action(
    db: Session,
    *,
    user_id: int,
    action_key: str,
    plan_date: date | None,
) -> tuple[dict, dict]:
    payload = build_daily_operating_plan(db, user_id, plan_date=plan_date)
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
    return payload, action


@router.get("/me")
def get_my_daily_plan(
    plan_date: Optional[date] = Query(None, description="默认今天"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户当天操作计划."""
    return build_daily_operating_plan(db, current_user.id, plan_date=plan_date)


@router.get("/review")
def get_my_daily_plan_review(
    window_days: int = Query(7, description="复盘窗口，仅支持 7/30/90 天"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取 Daily Plan 行动执行和关键指标变化复盘."""
    if window_days not in SUPPORTED_REVIEW_WINDOWS:
        raise HTTPException(status_code=422, detail="window_days 仅支持 7/30/90")
    return build_health_operating_review(db, user_id=current_user.id, window_days=window_days)


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
    payload, action = _load_daily_plan_action(
        db,
        user_id=current_user.id,
        action_key=action_key,
        plan_date=request.plan_date,
    )
    plan_date = _daily_plan_date(payload)
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


@router.post("/actions/{action_id}/events", response_model=DailyPlanActionEventResponse)
def record_my_daily_plan_action_event(
    action_id: str,
    request: DailyPlanActionEventRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """记录 Daily Plan 行动事件.

    新事件流使用 protocol 状态名, 用于后续验证闭环和 Agent 学习。
    """
    payload, action = _load_daily_plan_action(
        db,
        user_id=current_user.id,
        action_key=action_id,
        plan_date=request.plan_date,
    )
    plan_date = _daily_plan_date(payload)
    action_snapshot = dict(action)
    action_snapshot["event_type"] = request.event_type
    action_snapshot["event_payload"] = request.payload

    row = InterventionEvent(
        user_id=current_user.id,
        plan_id=payload.get("id"),
        plan_date=plan_date,
        action_key=action_id,
        action_domain=action.get("domain"),
        action_title=str(action.get("title") or action_id),
        feedback_status=request.event_type,
        reason=None,
        source="daily_plan",
        action_snapshot=action_snapshot,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return DailyPlanActionEventResponse(
        id=row.id,
        plan_id=row.plan_id,
        plan_date=row.plan_date,
        action_id=row.action_key,
        action_title=row.action_title,
        event_type=row.feedback_status,
        action_state=row.feedback_status,
        payload=request.payload,
    )
