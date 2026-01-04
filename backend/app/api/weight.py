"""体重追踪API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date, timedelta

from app.database import get_db
from app.models.weight import WeightRecord
from app.models.user import User
from app.schemas.weight import (
    WeightRecordCreate,
    WeightRecordUpdate,
    WeightRecordResponse,
    WeightStats,
)
from app.api.deps import get_current_user_required

router = APIRouter()


@router.post("/records", response_model=WeightRecordResponse)
def create_weight_record(
    record: WeightRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建体重记录（需要登录）"""
    user_id = current_user.id
    
    # 检查是否已有当天记录
    existing = db.query(WeightRecord).filter(
        WeightRecord.user_id == user_id,
        WeightRecord.record_date == record.record_date
    ).first()
    
    if existing:
        # 更新已有记录
        for key, value in record.model_dump(exclude={"user_id"}).items():
            if value is not None:
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    
    # 创建新记录
    record_data = record.model_dump()
    record_data["user_id"] = user_id
    db_record = WeightRecord(**record_data)
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


@router.get("/records/user/{user_id}", response_model=List[WeightRecordResponse])
def get_user_weight_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户体重记录（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    query = db.query(WeightRecord).filter(WeightRecord.user_id == current_user.id)
    
    if start_date:
        query = query.filter(WeightRecord.record_date >= start_date)
    if end_date:
        query = query.filter(WeightRecord.record_date <= end_date)
    
    records = query.order_by(desc(WeightRecord.record_date)).limit(limit).all()
    return records


@router.get("/records/me", response_model=List[WeightRecordResponse])
def get_my_weight_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户体重记录（需要登录）"""
    query = db.query(WeightRecord).filter(WeightRecord.user_id == current_user.id)
    
    if start_date:
        query = query.filter(WeightRecord.record_date >= start_date)
    if end_date:
        query = query.filter(WeightRecord.record_date <= end_date)
    
    records = query.order_by(desc(WeightRecord.record_date)).limit(limit).all()
    return records


@router.get("/records/user/{user_id}/latest", response_model=Optional[WeightRecordResponse])
def get_latest_weight(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取最新体重记录（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    record = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id
    ).order_by(desc(WeightRecord.record_date)).first()
    return record


@router.get("/records/user/{user_id}/stats", response_model=WeightStats)
def get_weight_stats(
    user_id: int,
    days: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取体重统计（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    start_date = date.today() - timedelta(days=days)
    
    records = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id,
        WeightRecord.record_date >= start_date
    ).order_by(desc(WeightRecord.record_date)).all()
    
    if not records:
        return WeightStats(total_records=0)
    
    weights = [r.weight for r in records if r.weight]
    
    # 计算30天变化
    weight_change = None
    if len(records) >= 2:
        latest = records[0].weight
        oldest = records[-1].weight
        weight_change = round(latest - oldest, 2)
    
    return WeightStats(
        current_weight=records[0].weight if records else None,
        highest_weight=max(weights) if weights else None,
        lowest_weight=min(weights) if weights else None,
        average_weight=round(sum(weights) / len(weights), 2) if weights else None,
        weight_change_30d=weight_change,
        total_records=len(records)
    )


@router.put("/records/{record_id}", response_model=WeightRecordResponse)
def update_weight_record(
    record_id: int,
    update_data: WeightRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新体重记录（需要登录，只能更新自己的）"""
    record = db.query(WeightRecord).filter(WeightRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改其他用户的数据")
    
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    
    db.commit()
    db.refresh(record)
    return record


@router.delete("/records/{record_id}")
def delete_weight_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除体重记录（需要登录，只能删除自己的）"""
    record = db.query(WeightRecord).filter(WeightRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除其他用户的数据")
    
    db.delete(record)
    db.commit()
    return {"message": "Record deleted successfully"}

