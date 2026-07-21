"""AI 洞察 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models import User, AIInsight, RealtimeRecommendation
from app.schemas.ai_insights import (
    AIInsightResponse, AIInsightListResponse,
    RealtimeRecommendationResponse,
    GenerateRecommendationRequest
)
from app.services.ai_insights_service import AIInsightsService

router = APIRouter()


def _resolve_user_city(db: Session, user_id: int) -> Optional[str]:
    from app.models.user_profile import UserProfile
    from app.services.location_resolver import resolve_effective_location
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    return resolve_effective_location(profile)["city"]


@router.get("/insights/daily", response_model=AIInsightListResponse)
async def get_daily_insights(
    days: int = Query(7, ge=1, le=30, description="获取最近几天的洞察"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取用户的每日健康洞察列表
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    insights = db.query(AIInsight).filter(
        AIInsight.user_id == current_user.id,
        AIInsight.review_date >= start_date,
        AIInsight.review_date <= end_date
    ).order_by(AIInsight.review_date.desc()).all()

    return AIInsightListResponse(
        items=insights,
        total=len(insights)
    )


@router.get("/insights/daily/{insight_date}", response_model=AIInsightResponse)
async def get_daily_insight_by_date(
    insight_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取指定日期的健康洞察
    """
    insight = db.query(AIInsight).filter(
        AIInsight.user_id == current_user.id,
        AIInsight.review_date == insight_date
    ).first()

    if not insight:
        raise HTTPException(status_code=404, detail="该日期的洞察不存在")

    return insight


@router.post("/insights/daily/generate", response_model=AIInsightResponse)
async def generate_daily_insight(
    target_date: Optional[date] = None,
    force_regenerate: bool = Query(False, description="是否强制重新生成（覆盖已有洞察）"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    手动触发生成每日洞察（通常由定时任务自动执行）

    参数:
    - target_date: 目标日期，默认为昨天
    - force_regenerate: 是否强制重新生成，默认为 False
    """
    service = AIInsightsService(db)
    insight = await service.generate_daily_insight(current_user.id, target_date, force_regenerate)

    if not insight:
        raise HTTPException(status_code=500, detail="生成洞察失败，请稍后重试")

    return insight


@router.post("/recommendations/realtime", response_model=RealtimeRecommendationResponse)
async def generate_realtime_recommendation(
    request: GenerateRecommendationRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    生成实时健康建议
    基于当前时间、位置、天气、身体状态等
    如果请求中未提供城市，自动从用户画像中获取
    """
    # 始终由后端推断城市（行程 > 手动 > IP检测 > profile），忽略前端传来的默认值
    city = _resolve_user_city(db, current_user.id) or request.city

    service = AIInsightsService(db)
    recommendation = await service.generate_realtime_recommendation(
        user_id=current_user.id,
        latitude=request.latitude,
        longitude=request.longitude,
        city=city
    )

    if not recommendation:
        raise HTTPException(status_code=500, detail="生成建议失败，请稍后重试")

    return recommendation


@router.get("/recommendations/latest", response_model=Optional[RealtimeRecommendationResponse])
async def get_latest_recommendation(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取用户最新的有效实时建议
    """
    from datetime import datetime

    recommendation = db.query(RealtimeRecommendation).filter(
        RealtimeRecommendation.user_id == current_user.id,
        RealtimeRecommendation.is_active == 1,
        RealtimeRecommendation.expires_at > datetime.now()
    ).order_by(RealtimeRecommendation.generated_at.desc()).first()

    return recommendation
