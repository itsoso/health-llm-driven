"""饮食记录API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date, timedelta, datetime, time

from app.database import get_db
from app.models.daily_health import DietRecord as DietRecordModel
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.diet import (
    MealType,
    DietRecordCreate,
    DietRecordUpdate,
    DietRecordResponse,
    DailyDietSummary,
    DietStats,
)

router = APIRouter()


@router.post("/records", response_model=DietRecordResponse)
def create_diet_record(
    record: DietRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建饮食记录（需要登录）"""
    # 转换meal_time为字符串
    record_dict = record.model_dump()
    if record_dict.get('meal_time'):
        record_dict['meal_time'] = record_dict['meal_time'].strftime('%H:%M')
    
    db_record = DietRecordModel(
        user_id=current_user.id,  # 使用当前登录用户ID
        record_date=record_dict['record_date'],
        meal_type=record_dict['meal_type'].value if isinstance(record_dict['meal_type'], MealType) else record_dict['meal_type'],
        food_items=record_dict['food_items'],
        calories=record_dict.get('calories'),
        protein=record_dict.get('protein'),
        carbs=record_dict.get('carbs'),
        fat=record_dict.get('fat'),
        fiber=record_dict.get('fiber'),
        notes=record_dict.get('notes'),
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    
    return _convert_to_response(db_record)


def _convert_to_response(record) -> DietRecordResponse:
    """转换为响应模型"""
    meal_time = None
    if hasattr(record, 'meal_time') and record.meal_time:
        if isinstance(record.meal_time, str):
            try:
                meal_time = datetime.strptime(record.meal_time, '%H:%M').time()
            except:
                meal_time = None
        elif isinstance(record.meal_time, time):
            meal_time = record.meal_time
    
    return DietRecordResponse(
        id=record.id,
        user_id=record.user_id,
        record_date=record.record_date,
        meal_type=MealType(record.meal_type) if record.meal_type else MealType.EXTRA,
        meal_time=meal_time,
        food_items=record.food_items or '',
        calories=record.calories,
        protein=record.protein,
        carbs=record.carbs,
        fat=record.fat,
        fiber=record.fiber,
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at if hasattr(record, 'updated_at') else None,
    )


@router.get("/records/user/{user_id}", response_model=List[DietRecordResponse])
def get_user_diet_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    meal_type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db)
):
    """获取用户饮食记录"""
    query = db.query(DietRecordModel).filter(DietRecordModel.user_id == user_id)
    
    if start_date:
        query = query.filter(DietRecordModel.record_date >= start_date)
    if end_date:
        query = query.filter(DietRecordModel.record_date <= end_date)
    if meal_type:
        query = query.filter(DietRecordModel.meal_type == meal_type)
    
    records = query.order_by(desc(DietRecordModel.record_date)).limit(limit).all()
    return [_convert_to_response(r) for r in records]


@router.get("/records/user/{user_id}/date/{record_date}", response_model=DailyDietSummary)
def get_daily_diet_summary(
    user_id: int,
    record_date: date,
    db: Session = Depends(get_db)
):
    """获取某日饮食汇总"""
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == user_id,
        DietRecordModel.record_date == record_date
    ).order_by(DietRecordModel.created_at).all()
    
    total_calories = sum(r.calories or 0 for r in records)
    total_protein = sum(r.protein or 0 for r in records)
    total_carbs = sum(r.carbs or 0 for r in records)
    total_fat = sum(r.fat or 0 for r in records)
    total_fiber = sum(r.fiber or 0 for r in records)
    
    return DailyDietSummary(
        record_date=record_date,
        total_calories=total_calories,
        total_protein=round(total_protein, 1),
        total_carbs=round(total_carbs, 1),
        total_fat=round(total_fat, 1),
        total_fiber=round(total_fiber, 1),
        meals_count=len(records),
        meals=[_convert_to_response(r) for r in records]
    )


@router.get("/records/user/{user_id}/stats", response_model=DietStats)
def get_diet_stats(
    user_id: int,
    days: int = Query(default=7, le=90),
    db: Session = Depends(get_db)
):
    """获取饮食统计"""
    start_date = date.today() - timedelta(days=days)
    
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == user_id,
        DietRecordModel.record_date >= start_date
    ).all()
    
    if not records:
        return DietStats(total_records=0, days_recorded=0)
    
    # 按日期分组统计
    daily_data = {}
    for r in records:
        d = str(r.record_date)
        if d not in daily_data:
            daily_data[d] = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
        daily_data[d]['calories'] += r.calories or 0
        daily_data[d]['protein'] += r.protein or 0
        daily_data[d]['carbs'] += r.carbs or 0
        daily_data[d]['fat'] += r.fat or 0
    
    days_count = len(daily_data)
    
    return DietStats(
        average_daily_calories=round(sum(d['calories'] for d in daily_data.values()) / days_count, 0) if days_count else None,
        average_daily_protein=round(sum(d['protein'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_carbs=round(sum(d['carbs'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_fat=round(sum(d['fat'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        total_records=len(records),
        days_recorded=days_count
    )


# ========== /me 端点 ==========

@router.get("/records/me", response_model=List[DietRecordResponse])
def get_my_diet_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    meal_type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户饮食记录（需要登录）"""
    query = db.query(DietRecordModel).filter(DietRecordModel.user_id == current_user.id)
    
    if start_date:
        query = query.filter(DietRecordModel.record_date >= start_date)
    if end_date:
        query = query.filter(DietRecordModel.record_date <= end_date)
    if meal_type:
        query = query.filter(DietRecordModel.meal_type == meal_type)
    
    records = query.order_by(desc(DietRecordModel.record_date)).limit(limit).all()
    return [_convert_to_response(r) for r in records]


@router.get("/records/me/date/{record_date}", response_model=DailyDietSummary)
def get_my_daily_diet_summary(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户某日饮食汇总（需要登录）"""
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == current_user.id,
        DietRecordModel.record_date == record_date
    ).order_by(DietRecordModel.created_at).all()
    
    total_calories = sum(r.calories or 0 for r in records)
    total_protein = sum(r.protein or 0 for r in records)
    total_carbs = sum(r.carbs or 0 for r in records)
    total_fat = sum(r.fat or 0 for r in records)
    total_fiber = sum(r.fiber or 0 for r in records)
    
    return DailyDietSummary(
        record_date=record_date,
        total_calories=total_calories,
        total_protein=round(total_protein, 1),
        total_carbs=round(total_carbs, 1),
        total_fat=round(total_fat, 1),
        total_fiber=round(total_fiber, 1),
        meals_count=len(records),
        meals=[_convert_to_response(r) for r in records]
    )


@router.get("/records/me/stats", response_model=DietStats)
def get_my_diet_stats(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户饮食统计（需要登录）"""
    start_date = date.today() - timedelta(days=days)
    
    records = db.query(DietRecordModel).filter(
        DietRecordModel.user_id == current_user.id,
        DietRecordModel.record_date >= start_date
    ).all()
    
    if not records:
        return DietStats(total_records=0, days_recorded=0)
    
    # 按日期分组统计
    daily_data = {}
    for r in records:
        d = str(r.record_date)
        if d not in daily_data:
            daily_data[d] = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
        daily_data[d]['calories'] += r.calories or 0
        daily_data[d]['protein'] += r.protein or 0
        daily_data[d]['carbs'] += r.carbs or 0
        daily_data[d]['fat'] += r.fat or 0
    
    days_count = len(daily_data)
    
    return DietStats(
        average_daily_calories=round(sum(d['calories'] for d in daily_data.values()) / days_count, 0) if days_count else None,
        average_daily_protein=round(sum(d['protein'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_carbs=round(sum(d['carbs'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        average_daily_fat=round(sum(d['fat'] for d in daily_data.values()) / days_count, 1) if days_count else None,
        total_records=len(records),
        days_recorded=days_count
    )


@router.put("/records/{record_id}", response_model=DietRecordResponse)
def update_diet_record(
    record_id: int,
    update_data: DietRecordUpdate,
    db: Session = Depends(get_db)
):
    """更新饮食记录"""
    record = db.query(DietRecordModel).filter(DietRecordModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    update_dict = update_data.model_dump(exclude_unset=True)
    if 'meal_type' in update_dict and update_dict['meal_type']:
        update_dict['meal_type'] = update_dict['meal_type'].value
    if 'meal_time' in update_dict and update_dict['meal_time']:
        update_dict['meal_time'] = update_dict['meal_time'].strftime('%H:%M')
    
    for key, value in update_dict.items():
        setattr(record, key, value)
    
    db.commit()
    db.refresh(record)
    return _convert_to_response(record)


@router.delete("/records/{record_id}")
def delete_diet_record(record_id: int, db: Session = Depends(get_db)):
    """删除饮食记录"""
    record = db.query(DietRecordModel).filter(DietRecordModel.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    db.delete(record)
    db.commit()
    return {"message": "Record deleted successfully"}

