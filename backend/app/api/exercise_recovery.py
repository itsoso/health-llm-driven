"""运动恢复评估 API

提供恢复就绪度、训练负荷（TRIMP/ACWR）、训练建议三个端点。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.exercise_recovery_service import exercise_recovery_service

router = APIRouter(prefix="/exercise-recovery", tags=["运动恢复"])


@router.get("/readiness")
async def get_recovery_readiness(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """综合恢复就绪度评估

    基于 HRV、睡眠质量、压力水平、身体电量四维评分。
    """
    return exercise_recovery_service.get_recovery_readiness(db, current_user.id)


@router.get("/training-load")
async def get_training_load(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """训练负荷与 ACWR（急性:慢性负荷比）

    计算 TRIMP 训练冲量和 7天/28天负荷比。
    """
    return exercise_recovery_service.get_training_load(db, current_user.id)


@router.get("/recommendation")
async def get_recommendation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """训练建议

    基于恢复就绪度和 ACWR 的二维矩阵决策。
    """
    return exercise_recovery_service.get_recommendation(db, current_user.id)
