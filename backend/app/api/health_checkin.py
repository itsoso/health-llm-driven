"""健康打卡API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.database import get_db
from app.schemas.health_checkin import HealthCheckinCreate, HealthCheckinResponse
from app.models.health_checkin import HealthCheckin
from app.models.user import User
from app.services.health_analysis import HealthAnalysisService
from app.api.deps import get_current_user_required

router = APIRouter()


@router.post("/", response_model=HealthCheckinResponse)
def create_health_checkin(
    checkin: HealthCheckinCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建健康打卡（需要登录）"""
    import logging
    logger = logging.getLogger(__name__)
    
    # 强制使用当前用户ID
    user_id = current_user.id
    logger.info(f"用户 {user_id} 保存打卡记录: {checkin.checkin_date}, notes={checkin.notes}")
    
    # 检查是否已存在该日期的打卡
    existing = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == user_id,
        HealthCheckin.checkin_date == checkin.checkin_date
    ).first()
    
    if existing:
        # 更新现有记录
        logger.info(f"更新现有记录 ID={existing.id}")
        for key, value in checkin.model_dump(exclude={"user_id", "checkin_date"}).items():
            if value is not None:
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    
    # 创建新记录
    checkin_data = checkin.model_dump()
    checkin_data["user_id"] = user_id
    
    # 如果没有提供个性化建议，尝试自动生成（失败不影响保存）
    if not checkin.personalized_advice:
        try:
            analysis_service = HealthAnalysisService()
            advice = analysis_service.generate_personalized_advice(
                db, user_id, checkin.checkin_date
            )
            checkin_data["personalized_advice"] = advice
        except Exception as e:
            logger.warning(f"生成个性化建议失败: {e}")
            checkin_data["personalized_advice"] = None
    
    logger.info(f"创建新记录: {checkin_data}")
    db_checkin = HealthCheckin(**checkin_data)
    db.add(db_checkin)
    db.commit()
    db.refresh(db_checkin)
    return db_checkin


# ========== /me 端点必须在 /user/{user_id} 之前定义 ==========

@router.get("/me/today", response_model=HealthCheckinResponse)
def get_my_today_checkin(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户今日健康打卡（需要登录）"""
    today = date.today()
    checkin = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == current_user.id,
        HealthCheckin.checkin_date == today
    ).first()
    if not checkin:
        raise HTTPException(status_code=404, detail="今日尚未打卡")
    return checkin


@router.get("/user/{user_id}", response_model=List[HealthCheckinResponse])
def get_user_checkins(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户的健康打卡记录（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    query = db.query(HealthCheckin).filter(HealthCheckin.user_id == current_user.id)
    
    if start_date:
        query = query.filter(HealthCheckin.checkin_date >= start_date)
    if end_date:
        query = query.filter(HealthCheckin.checkin_date <= end_date)
    
    checkins = query.order_by(HealthCheckin.checkin_date.desc()).offset(skip).limit(limit).all()
    return checkins


@router.get("/user/{user_id}/today", response_model=HealthCheckinResponse)
def get_today_checkin(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取今日健康打卡（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    today = date.today()
    checkin = db.query(HealthCheckin).filter(
        HealthCheckin.user_id == current_user.id,
        HealthCheckin.checkin_date == today
    ).first()
    
    if not checkin:
        raise HTTPException(status_code=404, detail="今日尚未打卡")
    return checkin

