"""
AI 日程编排 API

提供早间简报、日程安排、实时建议等功能
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import logging

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.ai_scheduler import ai_scheduler
from app.utils.timezone import get_china_now

router = APIRouter(prefix="/ai-scheduler", tags=["ai-scheduler"])
logger = logging.getLogger(__name__)


@router.get("/morning-briefing", summary="获取早间健康简报")
async def get_morning_briefing(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取个性化早间健康简报
    
    包含：
    - 昨日睡眠回顾
    - 身体状态概览
    - 今日目标
    - 重要提醒
    """
    try:
        briefing = ai_scheduler.generate_morning_briefing(db, current_user.id)
        return briefing
    except Exception as e:
        logger.error(f"生成早间简报失败: {e}")
        raise HTTPException(status_code=500, detail="生成早间简报失败")


@router.get("/daily-schedule", summary="获取今日日程安排")
async def get_daily_schedule(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取今日个性化日程安排
    
    基于用户画像和健康目标生成
    """
    try:
        schedule = ai_scheduler.generate_daily_schedule(db, current_user.id)
        return {
            "schedule": schedule,
            "generated_at": get_china_now().isoformat()
        }
    except Exception as e:
        logger.error(f"生成日程失败: {e}")
        raise HTTPException(status_code=500, detail="生成日程失败")


@router.get("/reminders", summary="获取当前时间段提醒")
async def get_current_reminders(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取当前时间段应该显示的提醒
    
    会根据用户状态和条件过滤
    """
    try:
        reminders = ai_scheduler.get_reminders_for_time(db, current_user.id)
        return {
            "reminders": reminders,
            "current_time": get_china_now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取提醒失败: {e}")
        raise HTTPException(status_code=500, detail="获取提醒失败")


@router.get("/recommendation", summary="获取实时健康建议")
async def get_time_aware_recommendation(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取时间感知的实时健康建议
    
    根据当前时间和用户今日状态给出最相关的建议
    """
    try:
        recommendation = ai_scheduler.get_time_aware_recommendation(db, current_user.id)
        return recommendation
    except Exception as e:
        logger.error(f"获取建议失败: {e}")
        raise HTTPException(status_code=500, detail="获取建议失败")


@router.get("/summary", summary="获取综合健康摘要")
async def get_health_summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取综合健康摘要，包括：
    - 早间简报
    - 当前建议
    - 当前提醒
    """
    try:
        briefing = ai_scheduler.generate_morning_briefing(db, current_user.id)
        recommendation = ai_scheduler.get_time_aware_recommendation(db, current_user.id)
        reminders = ai_scheduler.get_reminders_for_time(db, current_user.id)
        
        return {
            "briefing": briefing,
            "recommendation": recommendation,
            "reminders": reminders,
            "generated_at": get_china_now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取健康摘要失败: {e}")
        raise HTTPException(status_code=500, detail="获取健康摘要失败")
