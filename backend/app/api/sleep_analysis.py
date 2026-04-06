"""睡眠深度分析 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.services.sleep_analysis_service import sleep_analysis_service

router = APIRouter(prefix="/sleep", tags=["睡眠分析"])


@router.get("/deep-analysis", summary="深度睡眠分析")
async def get_deep_analysis(
    days: int = Query(default=14, ge=3, le=90, description="分析天数"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """多维度睡眠深度分析：架构、HRV恢复、一致性、个性化建议"""
    return sleep_analysis_service.get_deep_analysis(db, current_user.id, days)


@router.get("/debt", summary="睡眠债务")
async def get_sleep_debt(
    days: int = Query(default=14, ge=1, le=90, description="计算天数"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """累积睡眠债务计算：实际 vs 推荐时长，恢复计划"""
    return sleep_analysis_service.get_sleep_debt(db, current_user.id, days)


@router.get("/architecture", summary="睡眠架构分析")
async def get_sleep_architecture(
    days: int = Query(default=14, ge=3, le=90, description="分析天数"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """睡眠阶段百分比分析：深睡/浅睡/REM/清醒 vs 年龄基准"""
    return sleep_analysis_service.get_sleep_architecture(db, current_user.id, days)
