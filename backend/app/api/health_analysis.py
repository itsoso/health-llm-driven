"""健康分析API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date
from app.database import get_db
from app.services.health_analysis import HealthAnalysisService

router = APIRouter()


@router.get("/user/{user_id}/issues")
def analyze_health_issues(
    user_id: int,
    force_refresh: bool = Query(default=False, description="是否强制刷新缓存"),
    db: Session = Depends(get_db)
):
    """
    分析健康问题（带缓存）
    
    - 默认使用当天缓存的分析结果
    - 第二天自动重新分析
    - 可通过 force_refresh=true 强制刷新
    """
    service = HealthAnalysisService()
    return service.analyze_health_issues(db, user_id, force_refresh)


@router.get("/user/{user_id}/advice")
def get_personalized_advice(
    user_id: int,
    checkin_date: date,
    db: Session = Depends(get_db)
):
    """获取个性化建议"""
    service = HealthAnalysisService()
    advice = service.generate_personalized_advice(db, user_id, checkin_date)
    return {"advice": advice}

