"""
饮食推荐 API
提供智能饮食推荐、营养目标计算等功能
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.user import User
from app.api.auth import get_current_user_required
from app.api.admin import get_admin_user
from app.services.diet_recommendation import diet_recommendation_service

router = APIRouter(prefix="/diet-recommendation", tags=["diet-recommendation"])


@router.get("/me")
async def get_my_diet_recommendation(
    meal_type: Optional[str] = Query(None, description="餐次类型: breakfast/lunch/dinner/snack"),
    debug: bool = Query(False, description="是否返回调试信息"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取我的智能饮食推荐

    返回内容：
    - 每日营养目标（卡路里、蛋白质、碳水、脂肪）
    - 今日已摄入
    - 剩余可摄入
    - 摄入进度百分比
    - 用户代谢信息（BMR、TDEE）
    """
    return await diet_recommendation_service.generate_diet_recommendation(
        db=db,
        user_id=current_user.id,
        meal_type=meal_type,
        debug=debug
    )


@router.get("/{user_id}")
async def get_user_diet_recommendation(
    user_id: int,
    meal_type: Optional[str] = Query(None, description="餐次类型: breakfast/lunch/dinner/snack"),
    debug: bool = Query(False, description="是否返回调试信息"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取指定用户的饮食推荐（管理员功能）
    """
    return await diet_recommendation_service.generate_diet_recommendation(
        db=db,
        user_id=user_id,
        meal_type=meal_type,
        debug=debug
    )
