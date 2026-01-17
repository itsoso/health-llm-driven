"""
数字孪生 API - executor.life 健康模块

提供用户数字健康模型的访问接口
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.digital_twin import get_digital_twin

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/report", summary="获取数字孪生完整报告")
async def get_digital_twin_report(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取用户的完整数字孪生报告
    
    包含：
    - 基础生理指标（BMR、TDEE、心率区间等）
    - 健康评分（睡眠、运动、身体状态、身体成分）
    - 趋势分析（睡眠、运动、体重趋势）
    - 个性化建议
    """
    try:
        twin = get_digital_twin(db, current_user.id)
        report = twin.generate_digital_twin_report()
        return report
    except Exception as e:
        logger.error(f"生成数字孪生报告失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成报告失败: {str(e)}"
        )


@router.get("/physiological", summary="获取基础生理指标")
async def get_physiological_metrics(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取基础生理指标
    
    包含：
    - BMR（基础代谢率）
    - TDEE（每日总能量消耗）
    - 目标心率区间
    - 理想体重范围
    """
    twin = get_digital_twin(db, current_user.id)
    
    return {
        'bmr': twin.calculate_bmr(),
        'tdee': twin.calculate_tdee(),
        'heart_rate_zones': twin.calculate_target_heart_rate_zones(),
        'ideal_weight_range': twin.calculate_ideal_weight_range()
    }


@router.get("/health-score", summary="获取健康评分")
async def get_health_score(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取综合健康评分
    
    评分维度：
    - 睡眠 (25%)
    - 运动 (25%)
    - 身体状态 (25%)
    - 身体成分 (25%)
    """
    twin = get_digital_twin(db, current_user.id)
    return twin.calculate_health_score()


@router.get("/trends/sleep", summary="获取睡眠趋势分析")
async def get_sleep_trend(
    days: int = 30,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析睡眠趋势"""
    twin = get_digital_twin(db, current_user.id)
    return twin.analyze_sleep_trend(days)


@router.get("/trends/exercise", summary="获取运动趋势分析")
async def get_exercise_trend(
    days: int = 30,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析运动趋势"""
    twin = get_digital_twin(db, current_user.id)
    return twin.analyze_exercise_trend(days)


@router.get("/trends/body-composition", summary="获取身体成分趋势")
async def get_body_composition_trend(
    days: int = 90,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析身体成分（体重、体脂）趋势"""
    twin = get_digital_twin(db, current_user.id)
    return twin.analyze_body_composition_trend(days)


@router.get("/tdee-calculator", summary="TDEE计算器")
async def calculate_tdee(
    activity_level: str = "moderate",
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    计算不同活动水平下的 TDEE
    
    活动水平:
    - sedentary: 久坐，几乎不运动
    - light: 轻度活动，每周1-3天
    - moderate: 中等活动，每周3-5天
    - active: 高度活动，每周6-7天
    - very_active: 非常活跃，体力劳动
    """
    twin = get_digital_twin(db, current_user.id)
    bmr = twin.calculate_bmr()
    
    if bmr is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先完善个人资料（身高、体重、出生日期、性别）"
        )
    
    activity_multipliers = {
        'sedentary': 1.2,
        'light': 1.375,
        'moderate': 1.55,
        'active': 1.725,
        'very_active': 1.9
    }
    
    tdee_by_level = {
        level: round(bmr * mult, 0)
        for level, mult in activity_multipliers.items()
    }
    
    return {
        'bmr': bmr,
        'selected_activity_level': activity_level,
        'selected_tdee': tdee_by_level.get(activity_level, tdee_by_level['moderate']),
        'tdee_by_activity_level': tdee_by_level,
        'calorie_targets': {
            'maintain': tdee_by_level.get(activity_level),
            'mild_loss': tdee_by_level.get(activity_level) - 250,  # 0.25kg/week
            'moderate_loss': tdee_by_level.get(activity_level) - 500,  # 0.5kg/week
            'mild_gain': tdee_by_level.get(activity_level) + 250,
            'moderate_gain': tdee_by_level.get(activity_level) + 500
        }
    }
