"""统一健康议程 API(R1)。只读投影:今日该做什么,一处可见、跨端一致。"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services import agenda_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agenda", tags=["统一健康议程"])


@router.get("/today")
async def agenda_today(
    followup_within_days: int = Query(default=14, le=120),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """今日统一议程:三域协议待办 + 近 N 天到期复查,按优先级排序。"""
    return agenda_service.today(db, current_user.id, followup_within_days)
