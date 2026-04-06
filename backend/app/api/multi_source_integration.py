"""多源数据整合 API"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.multi_source_integration_service import multi_source_integration_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health/integration", tags=["多源数据整合"])


@router.get("/profile")
async def get_integrated_profile(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """综合健康画像 — 整合所有数据源的统一快照"""
    logger.info(f"[Integration] 用户 {current_user.id} 请求综合健康画像")
    return multi_source_integration_service.get_integrated_profile(db=db, user_id=current_user.id)


@router.get("/completeness")
async def get_data_completeness(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """数据完整性报告 — 各数据源覆盖率和缺失分析"""
    logger.info(f"[Integration] 用户 {current_user.id} 请求数据完整性报告")
    return multi_source_integration_service.get_data_completeness(db=db, user_id=current_user.id)


@router.get("/correlations")
async def get_correlations(
    days: int = Query(default=30, ge=14, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """跨模态关联分析 — 发现不同数据源之间的统计关联"""
    logger.info(f"[Integration] 用户 {current_user.id} 请求关联分析 {days}天")
    return multi_source_integration_service.find_correlations(db=db, user_id=current_user.id, days=days)
