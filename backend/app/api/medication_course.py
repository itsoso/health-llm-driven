"""用药疗程 → 复查闭环 API。

GET  /medication-course/upcoming   即将结束的疗程 + 建议复查
POST /medication-course/materialize 物化为 ReviewSchedule(复查日历)
分析逻辑在 service,对话(agent 注入)复用同一套 —— 三端共享。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.medication_course_service import (
    ensure_review_schedules,
    upcoming_course_completions,
)

router = APIRouter()


@router.get("/upcoming", summary="即将结束的用药疗程 + 建议复查")
def upcoming(
    within_days: int = 45,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return {"items": upcoming_course_completions(db, current_user.id, within_days)}


@router.post("/materialize", summary="把即将结束疗程的复查写入复查日历(ReviewSchedule)")
def materialize(
    within_days: int = 45,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """幂等:已存在的复查项不重复建。返回 {created, skipped}。"""
    return ensure_review_schedules(db, current_user.id, within_days)
