"""健康评分 API"""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import date

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.health_score_service import health_score_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health-score", tags=["健康评分"])


@router.get("/daily/me")
async def get_my_daily_score(
    target_date: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """获取我的每日健康评分"""
    logger.info(f"[HealthScoreAPI] 用户 {current_user.id} 请求每日评分")
    d = date.fromisoformat(target_date) if target_date else None
    return health_score_service.calculate_daily_score(
        db=db, user_id=current_user.id, target_date=d,
    )


@router.get("/trend/me")
async def get_my_score_trend(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """获取我的评分趋势"""
    logger.info(f"[HealthScoreAPI] 用户 {current_user.id} 请求评分趋势 {days}天")
    return health_score_service.get_score_trend(
        db=db, user_id=current_user.id, days=days,
    )
