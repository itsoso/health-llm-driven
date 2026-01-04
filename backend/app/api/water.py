"""饮水追踪API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date, timedelta, datetime, time

from app.database import get_db
from app.models.daily_health import WaterIntake as WaterIntakeModel
from app.models.user import User
from app.schemas.water import (
    WaterRecordCreate,
    WaterRecordUpdate,
    WaterRecordResponse,
    DailyWaterSummary,
    WaterStats,
)
from app.api.deps import get_current_user_required

router = APIRouter()

# 每日目标饮水量（毫升）
DAILY_WATER_TARGET = 2000


def _convert_to_response(record) -> WaterRecordResponse:
    """转换为响应模型"""
    drink_time = None
    if hasattr(record, 'intake_time') and record.intake_time:
        if isinstance(record.intake_time, datetime):
            drink_time = record.intake_time.time()
        elif isinstance(record.intake_time, time):
            drink_time = record.intake_time
    
    return WaterRecordResponse(
        id=record.id,
        user_id=record.user_id,
        record_date=record.record_date,
        amount=record.amount or 0,
        drink_time=drink_time,
        drink_type=record.drink_type if hasattr(record, 'drink_type') else None,
        notes=record.notes if hasattr(record, 'notes') else None,
        created_at=record.created_at,
        updated_at=record.updated_at if hasattr(record, 'updated_at') else None,
    )


@router.post("/records", response_model=WaterRecordResponse)
def create_water_record(
    record: WaterRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建饮水记录（需要登录）"""
    intake_time = None
    if record.drink_time:
        intake_time = datetime.combine(record.record_date, record.drink_time)
    
    db_record = WaterIntakeModel(
        user_id=current_user.id,
        record_date=record.record_date,
        amount=record.amount,
        intake_time=intake_time,
        drink_type=record.drink_type,
        notes=record.notes,
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    
    return _convert_to_response(db_record)


@router.get("/records/user/{user_id}", response_model=List[WaterRecordResponse])
def get_user_water_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=50, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户饮水记录（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    query = db.query(WaterIntakeModel).filter(WaterIntakeModel.user_id == current_user.id)
    
    if start_date:
        query = query.filter(WaterIntakeModel.record_date >= start_date)
    if end_date:
        query = query.filter(WaterIntakeModel.record_date <= end_date)
    
    records = query.order_by(desc(WaterIntakeModel.record_date), desc(WaterIntakeModel.created_at)).limit(limit).all()
    return [_convert_to_response(r) for r in records]


@router.get("/records/user/{user_id}/date/{record_date}", response_model=DailyWaterSummary)
def get_daily_water_summary(
    user_id: int,
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取某日饮水汇总（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    records = db.query(WaterIntakeModel).filter(
        WaterIntakeModel.user_id == current_user.id,
        WaterIntakeModel.record_date == record_date
    ).order_by(WaterIntakeModel.created_at).all()
    
    total_amount = sum(r.amount or 0 for r in records)
    progress = round((total_amount / DAILY_WATER_TARGET) * 100, 1) if DAILY_WATER_TARGET > 0 else 0
    
    return DailyWaterSummary(
        record_date=record_date,
        total_amount=total_amount,
        target_amount=DAILY_WATER_TARGET,
        progress_percentage=min(progress, 100),
        records_count=len(records),
        records=[_convert_to_response(r) for r in records]
    )


@router.post("/records/quick", response_model=WaterRecordResponse)
def quick_add_water(
    amount: int = Query(default=250, description="饮水量(ml)"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """快速添加饮水（默认250ml，需要登录）"""
    now = datetime.now()
    db_record = WaterIntakeModel(
        user_id=current_user.id,
        record_date=now.date(),
        amount=amount,
        intake_time=now,
        drink_type="水",
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    
    return _convert_to_response(db_record)


@router.get("/records/user/{user_id}/stats", response_model=WaterStats)
def get_water_stats(
    user_id: int,
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取饮水统计（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    start_date = date.today() - timedelta(days=days)
    
    records = db.query(WaterIntakeModel).filter(
        WaterIntakeModel.user_id == current_user.id,
        WaterIntakeModel.record_date >= start_date
    ).all()
    
    if not records:
        return WaterStats(total_records=0, days_recorded=0)
    
    # 按日期分组统计
    daily_amounts = {}
    for r in records:
        d = str(r.record_date)
        if d not in daily_amounts:
            daily_amounts[d] = 0
        daily_amounts[d] += r.amount or 0
    
    days_count = len(daily_amounts)
    amounts = list(daily_amounts.values())
    days_reached = sum(1 for a in amounts if a >= DAILY_WATER_TARGET)
    
    return WaterStats(
        average_daily_amount=round(sum(amounts) / days_count, 0) if days_count else None,
        highest_daily_amount=max(amounts) if amounts else None,
        lowest_daily_amount=min(amounts) if amounts else None,
        total_records=len(records),
        days_recorded=days_count,
        days_reached_target=days_reached,
        target_percentage=round((days_reached / days_count) * 100, 1) if days_count else 0
    )


@router.put("/records/{record_id}", response_model=WaterRecordResponse)
def update_water_record(
    record_id: int,
    update_data: WaterRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新饮水记录（需要登录，只能更新自己的）"""
    record = db.query(WaterIntakeModel).filter(WaterIntakeModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改其他用户的数据")
    
    update_dict = update_data.model_dump(exclude_unset=True)
    if 'drink_time' in update_dict and update_dict['drink_time']:
        update_dict['intake_time'] = datetime.combine(record.record_date, update_dict.pop('drink_time'))
    
    for key, value in update_dict.items():
        if hasattr(record, key):
            setattr(record, key, value)
    
    db.commit()
    db.refresh(record)
    return _convert_to_response(record)


@router.delete("/records/{record_id}")
def delete_water_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除饮水记录（需要登录，只能删除自己的）"""
    record = db.query(WaterIntakeModel).filter(WaterIntakeModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除其他用户的数据")
    
    db.delete(record)
    db.commit()
    return {"message": "Record deleted successfully"}

