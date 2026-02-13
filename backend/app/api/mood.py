"""情绪追踪 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta

from app.database import get_db
from app.models.user import User
from app.schemas.mood import (
    MoodRecordCreate,
    MoodRecordUpdate,
    MoodRecordResponse,
    MoodStats,
    MoodCalendar,
)
from app.api.deps import get_current_user_required
from app.services.mood_service import mood_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mood", tags=["情绪追踪"])


@router.post("/records", response_model=MoodRecordResponse)
async def create_mood_record(
    data: MoodRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建情绪记录"""
    logger.info(f"[MoodAPI] 用户 {current_user.id} 创建情绪记录")

    record = mood_service.create_record(
        db=db,
        user_id=current_user.id,
        record_date=data.record_date,
        mood_score=data.mood_score,
        mood_tags=data.mood_tags,
        energy_level=data.energy_level,
        stress_level=data.stress_level,
        anxiety_level=data.anxiety_level,
        sleep_quality=data.sleep_quality,
        journal=data.journal,
        triggers=data.triggers,
        coping_methods=data.coping_methods,
    )
    return MoodRecordResponse.model_validate(record)


@router.get("/records/me", response_model=List[MoodRecordResponse])
async def get_my_mood_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户情绪记录列表"""
    records = mood_service.get_records(
        db=db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return [MoodRecordResponse.model_validate(r) for r in records]


@router.get("/records/me/today", response_model=Optional[MoodRecordResponse])
async def get_today_mood(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取今日情绪记录"""
    record = mood_service.get_today_record(db=db, user_id=current_user.id)
    if record:
        return MoodRecordResponse.model_validate(record)
    return None


@router.get("/records/{record_id}", response_model=MoodRecordResponse)
async def get_mood_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取单条情绪记录"""
    record = mood_service.get_record(db=db, record_id=record_id, user_id=current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return MoodRecordResponse.model_validate(record)


@router.put("/records/{record_id}", response_model=MoodRecordResponse)
async def update_mood_record(
    record_id: int,
    data: MoodRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新情绪记录"""
    update_data = data.model_dump(exclude_unset=True)
    record = mood_service.update_record(
        db=db,
        record_id=record_id,
        user_id=current_user.id,
        **update_data,
    )
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return MoodRecordResponse.model_validate(record)


@router.delete("/records/{record_id}")
async def delete_mood_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除情绪记录"""
    success = mood_service.delete_record(
        db=db,
        record_id=record_id,
        user_id=current_user.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"message": "记录已删除"}


@router.get("/stats/me", response_model=MoodStats)
async def get_mood_stats(
    days: int = Query(default=7, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取情绪统计"""
    return mood_service.get_stats(
        db=db,
        user_id=current_user.id,
        days=days,
    )


@router.get("/calendar/me", response_model=MoodCalendar)
async def get_mood_calendar(
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取情绪日历"""
    return mood_service.get_calendar(
        db=db,
        user_id=current_user.id,
        year=year,
        month=month,
    )
