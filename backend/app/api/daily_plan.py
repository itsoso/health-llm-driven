"""Daily Operating Plan API."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.daily_operating_plan import build_daily_operating_plan

router = APIRouter(prefix="/daily-plan", tags=["daily-plan"])


@router.get("/me")
def get_my_daily_plan(
    plan_date: Optional[date] = Query(None, description="默认今天"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户当天操作计划."""
    return build_daily_operating_plan(db, current_user.id, plan_date=plan_date)
