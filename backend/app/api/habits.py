"""习惯追踪 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import List, Optional
from datetime import date, timedelta
from app.database import get_db
from app.models.habit import HabitDefinition, HabitRecord
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.habit import (
    HabitDefinitionCreate,
    HabitDefinitionUpdate,
    HabitDefinitionResponse,
    HabitRecordCreate,
    HabitRecordResponse,
    HabitBatchCheckin,
    HabitWithRecord,
    HabitStats
)

router = APIRouter()


def calculate_streak(db: Session, habit_id: int, end_date: date) -> int:
    """计算连续打卡天数"""
    streak = 0
    current_date = end_date
    
    while True:
        record = db.query(HabitRecord).filter(
            HabitRecord.habit_id == habit_id,
            HabitRecord.record_date == current_date,
            HabitRecord.completed == True
        ).first()
        
        if not record:
            break
        
        streak += 1
        current_date = current_date - timedelta(days=1)
    
    return streak


# ========== 习惯定义 ==========

@router.post("/definitions", response_model=HabitDefinitionResponse)
def create_habit(
    habit: HabitDefinitionCreate,
    db: Session = Depends(get_db)
):
    """创建习惯"""
    db_habit = HabitDefinition(**habit.model_dump())
    db.add(db_habit)
    db.commit()
    db.refresh(db_habit)
    return db_habit


@router.get("/definitions/user/{user_id}", response_model=List[HabitDefinitionResponse])
def get_user_habits(
    user_id: int,
    active_only: bool = True,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取用户的习惯列表"""
    query = db.query(HabitDefinition).filter(HabitDefinition.user_id == user_id)
    if active_only:
        query = query.filter(HabitDefinition.is_active == True)
    if category:
        query = query.filter(HabitDefinition.category == category)
    return query.order_by(HabitDefinition.sort_order, HabitDefinition.id).all()


@router.put("/definitions/{habit_id}", response_model=HabitDefinitionResponse)
def update_habit(
    habit_id: int,
    update_data: HabitDefinitionUpdate,
    db: Session = Depends(get_db)
):
    """更新习惯"""
    habit = db.query(HabitDefinition).filter(HabitDefinition.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="习惯不存在")
    
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(habit, key, value)
    
    db.commit()
    db.refresh(habit)
    return habit


@router.delete("/definitions/{habit_id}")
def delete_habit(
    habit_id: int,
    db: Session = Depends(get_db)
):
    """删除习惯"""
    habit = db.query(HabitDefinition).filter(HabitDefinition.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="习惯不存在")
    
    db.delete(habit)
    db.commit()
    return {"message": "删除成功"}


# ========== 习惯打卡 ==========

@router.post("/records", response_model=HabitRecordResponse)
def create_habit_record(
    record: HabitRecordCreate,
    db: Session = Depends(get_db)
):
    """创建/更新习惯打卡记录"""
    existing = db.query(HabitRecord).filter(
        HabitRecord.habit_id == record.habit_id,
        HabitRecord.record_date == record.record_date
    ).first()
    
    if existing:
        existing.completed = record.completed
        existing.notes = record.notes
        db.commit()
        db.refresh(existing)
        return existing
    
    db_record = HabitRecord(**record.model_dump())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


@router.post("/records/batch")
def batch_checkin(
    batch: HabitBatchCheckin,
    db: Session = Depends(get_db)
):
    """批量习惯打卡"""
    results = []
    for checkin in batch.checkins:
        habit_id = checkin.get("habit_id")
        completed = checkin.get("completed", False)
        
        existing = db.query(HabitRecord).filter(
            HabitRecord.habit_id == habit_id,
            HabitRecord.record_date == batch.record_date
        ).first()
        
        if existing:
            existing.completed = completed
            db.commit()
            results.append({"habit_id": habit_id, "action": "updated"})
        else:
            record = HabitRecord(
                habit_id=habit_id,
                user_id=batch.user_id,
                record_date=batch.record_date,
                completed=completed
            )
            db.add(record)
            results.append({"habit_id": habit_id, "action": "created"})
    
    db.commit()
    return {"message": "批量打卡成功", "results": results}


@router.get("/records/user/{user_id}/date/{record_date}", response_model=List[HabitWithRecord])
def get_user_habits_with_records(
    user_id: int,
    record_date: date,
    db: Session = Depends(get_db)
):
    """获取用户某天的习惯列表及打卡状态"""
    habits = db.query(HabitDefinition).filter(
        HabitDefinition.user_id == user_id,
        HabitDefinition.is_active == True
    ).order_by(HabitDefinition.category, HabitDefinition.sort_order).all()
    
    result = []
    for habit in habits:
        record = db.query(HabitRecord).filter(
            HabitRecord.habit_id == habit.id,
            HabitRecord.record_date == record_date
        ).first()
        
        streak = calculate_streak(db, habit.id, record_date) if record and record.completed else 0
        
        result.append(HabitWithRecord(
            habit=HabitDefinitionResponse.model_validate(habit),
            record=HabitRecordResponse.model_validate(record) if record else None,
            streak=streak
        ))
    
    return result


@router.get("/records/user/{user_id}/stats", response_model=List[HabitStats])
def get_habit_stats(
    user_id: int,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """获取习惯统计"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    
    habits = db.query(HabitDefinition).filter(
        HabitDefinition.user_id == user_id,
        HabitDefinition.is_active == True
    ).all()
    
    stats = []
    for habit in habits:
        records = db.query(HabitRecord).filter(
            HabitRecord.habit_id == habit.id,
            HabitRecord.record_date >= start_date,
            HabitRecord.record_date <= end_date
        ).all()
        
        completed_count = sum(1 for r in records if r.completed)
        current_streak = calculate_streak(db, habit.id, end_date)
        
        # 计算最长连续打卡
        longest_streak = 0
        current_run = 0
        for i in range(days):
            check_date = start_date + timedelta(days=i)
            record = next((r for r in records if r.record_date == check_date), None)
            if record and record.completed:
                current_run += 1
                longest_streak = max(longest_streak, current_run)
            else:
                current_run = 0
        
        stats.append(HabitStats(
            habit_id=habit.id,
            habit_name=habit.name,
            total_days=days,
            completed_days=completed_count,
            completion_rate=round(completed_count / days * 100, 1),
            current_streak=current_streak,
            longest_streak=longest_streak
        ))
    
    return stats


@router.get("/records/user/{user_id}/today-summary")
def get_today_summary(
    user_id: int,
    db: Session = Depends(get_db)
):
    """获取今日习惯打卡汇总"""
    today = date.today()
    
    habits = db.query(HabitDefinition).filter(
        HabitDefinition.user_id == user_id,
        HabitDefinition.is_active == True
    ).all()
    
    total = len(habits)
    completed = 0
    
    for habit in habits:
        record = db.query(HabitRecord).filter(
            HabitRecord.habit_id == habit.id,
            HabitRecord.record_date == today,
            HabitRecord.completed == True
        ).first()
        if record:
            completed += 1
    
    return {
        "date": today.isoformat(),
        "total_habits": total,
        "completed": completed,
        "pending": total - completed,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0
    }


# ========== /me 端点 ==========

@router.get("/me/date/{record_date}", response_model=List[HabitWithRecord])
def get_my_habits_with_records(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户某天的习惯列表及打卡状态（需要登录）"""
    habits = db.query(HabitDefinition).filter(
        HabitDefinition.user_id == current_user.id,
        HabitDefinition.is_active == True
    ).order_by(HabitDefinition.category, HabitDefinition.sort_order).all()
    
    result = []
    for habit in habits:
        record = db.query(HabitRecord).filter(
            HabitRecord.habit_id == habit.id,
            HabitRecord.record_date == record_date
        ).first()
        
        streak = calculate_streak(db, habit.id, record_date) if record and record.completed else 0
        
        result.append(HabitWithRecord(
            habit=HabitDefinitionResponse.model_validate(habit),
            record=HabitRecordResponse.model_validate(record) if record else None,
            current_streak=streak
        ))
    
    return result


@router.get("/me/stats", response_model=List[HabitStats])
def get_my_habit_stats(
    days: int = 30,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户习惯统计（需要登录）"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    
    habits = db.query(HabitDefinition).filter(
        HabitDefinition.user_id == current_user.id,
        HabitDefinition.is_active == True
    ).all()
    
    stats = []
    for habit in habits:
        records = db.query(HabitRecord).filter(
            HabitRecord.habit_id == habit.id,
            HabitRecord.record_date >= start_date,
            HabitRecord.record_date <= end_date
        ).all()
        
        completed_count = sum(1 for r in records if r.completed)
        current_streak = calculate_streak(db, habit.id, end_date)
        
        stats.append(HabitStats(
            habit_id=habit.id,
            habit_name=habit.name,
            category=habit.category,
            total_days=days,
            completed_days=completed_count,
            completion_rate=round(completed_count / days * 100, 1),
            current_streak=current_streak,
            best_streak=0  # TODO: 计算最佳连续天数
        ))
    
    return stats


@router.get("/me/today-summary")
def get_my_today_summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户今日习惯打卡汇总（需要登录）"""
    today = date.today()
    
    habits = db.query(HabitDefinition).filter(
        HabitDefinition.user_id == current_user.id,
        HabitDefinition.is_active == True
    ).all()
    
    total = len(habits)
    completed = 0
    
    for habit in habits:
        record = db.query(HabitRecord).filter(
            HabitRecord.habit_id == habit.id,
            HabitRecord.record_date == today,
            HabitRecord.completed == True
        ).first()
        if record:
            completed += 1
    
    return {
        "date": today.isoformat(),
        "total_habits": total,
        "completed": completed,
        "pending": total - completed,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0
    }

