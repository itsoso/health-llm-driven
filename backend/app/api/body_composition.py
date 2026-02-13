"""身体成分分析 API"""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.body_composition_service import body_composition_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/body-composition", tags=["身体成分"])


@router.get("/trend/me")
async def get_body_composition_trend(
    days: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """获取身体成分趋势"""
    return body_composition_service.get_composition_trend(
        db=db, user_id=current_user.id, days=days,
    )


@router.get("/analysis/me")
async def get_body_analysis(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """获取身体成分分析"""
    return body_composition_service.get_body_analysis(
        db=db, user_id=current_user.id,
    )
