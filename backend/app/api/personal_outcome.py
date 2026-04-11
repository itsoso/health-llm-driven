"""Personal Outcome API

长期健康改善档案：时间序列 × 干预事件 × 摘要。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.personal_outcome_service import PersonalOutcomeService

router = APIRouter(prefix="/personal-outcome", tags=["personal-outcome"])

_service = PersonalOutcomeService()


@router.get("/me/timeline")
def get_my_timeline(
    range: str = Query("2y", pattern="^(6m|1y|2y|all)$"),
    granularity: str = Query("month", pattern="^(week|month)$"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的个人健康改善时间线。

    range:
    - 6m: 最近 180 天
    - 1y: 最近 365 天
    - 2y: 最近 730 天
    - all: 全部历史
    granularity:
    - week: 按 ISO 周聚合
    - month: 按月聚合（默认）
    """
    return _service.get_timeline(
        db=db,
        user_id=current_user.id,
        range_key=range,
        granularity=granularity,
    )


@router.get("/me/events/{event_id}/impact")
def get_my_event_impact(
    event_id: str,
    window_days: int = Query(30, ge=7, le=180),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取单个干预事件前后窗口的指标对比。

    event_id 规范：
    - sup-{definition_id}
    - exam-{exam_id}
    - milestone-garmin-start
    """
    return _service.get_event_impact(
        db=db,
        user_id=current_user.id,
        event_id=event_id,
        window_days=window_days,
    )
