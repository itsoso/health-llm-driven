"""健康打卡API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.database import get_db
from app.schemas.health_checkin import HealthCheckinCreate, HealthCheckinResponse
from app.models.health_checkin import HealthCheckin
from app.services.health_analysis import HealthAnalysisService

router = APIRouter()


@router.post("/", response_model=HealthCheckinResponse)
def create_health_checkin(
    checkin: HealthCheckinCreate,
    db: Session = Depends(get_db)
):
    """创建健康打卡"""
    # 检查是否已存在该日期的打卡
    existing = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == checkin.user_id,
        HealthCheckin.checkin_date == checkin.checkin_date
    ).first()
    
    if existing:
        # 更新现有记录
        for key, value in checkin.model_dump(exclude={"user_id", "checkin_date"}).items():
            if value is not None:
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    
    # 如果没有提供个性化建议，自动生成
    if not checkin.personalized_advice:
        analysis_service = HealthAnalysisService()
        advice = analysis_service.generate_personalized_advice(
            db, checkin.user_id, checkin.checkin_date
        )
        checkin.personalized_advice = advice
    
    db_checkin = HealthCheckin(**checkin.model_dump())
    db.add(db_checkin)
    db.commit()
    db.refresh(db_checkin)
    return db_checkin


@router.get("/user/{user_id}", response_model=List[HealthCheckinResponse])
def get_user_checkins(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取用户的健康打卡记录"""
    query = db.query(HealthCheckin).filter(HealthCheckin.user_id == user_id)
    
    if start_date:
        query = query.filter(HealthCheckin.checkin_date >= start_date)
    if end_date:
        query = query.filter(HealthCheckin.checkin_date <= end_date)
    
    checkins = query.order_by(HealthCheckin.checkin_date.desc()).offset(skip).limit(limit).all()
    return checkins


@router.get("/user/{user_id}/today", response_model=HealthCheckinResponse)
def get_today_checkin(
    user_id: int,
    db: Session = Depends(get_db)
):
    """获取今日健康打卡"""
    today = date.today()
    checkin = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == user_id,
        HealthCheckin.checkin_date == today
    ).first()
    
    if not checkin:
        raise HTTPException(status_code=404, detail="今日尚未打卡")
    return checkin

