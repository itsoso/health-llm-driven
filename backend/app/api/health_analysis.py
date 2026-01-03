"""健康分析API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date
from app.database import get_db
from app.services.health_analysis import HealthAnalysisService

router = APIRouter()


@router.get("/user/{user_id}/issues")
def analyze_health_issues(
    user_id: int,
    db: Session = Depends(get_db)
):
    """分析健康问题"""
    service = HealthAnalysisService()
    return service.analyze_health_issues(db, user_id)


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

