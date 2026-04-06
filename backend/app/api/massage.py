"""按摩/理疗追踪API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date, timedelta

from app.database import get_db
from app.models.massage import MassageRecord
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.massage import (
    MassageRecordCreate,
    MassageRecordUpdate,
    MassageRecordResponse,
    MassageStats,
)

router = APIRouter()


@router.post("/records", response_model=MassageRecordResponse)
def create_record(
    record: MassageRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    db_record = MassageRecord(user_id=current_user.id, **record.model_dump())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


@router.get("/records", response_model=List[MassageRecordResponse])
def list_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    q = db.query(MassageRecord).filter(MassageRecord.user_id == current_user.id)
    if start_date:
        q = q.filter(MassageRecord.record_date >= start_date)
    if end_date:
        q = q.filter(MassageRecord.record_date <= end_date)
    return q.order_by(desc(MassageRecord.record_date)).offset(offset).limit(limit).all()


@router.get("/records/{record_id}", response_model=MassageRecordResponse)
def get_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(MassageRecord).filter(
        MassageRecord.id == record_id,
        MassageRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


@router.put("/records/{record_id}", response_model=MassageRecordResponse)
def update_record(
    record_id: int,
    update: MassageRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(MassageRecord).filter(
        MassageRecord.id == record_id,
        MassageRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/records/{record_id}")
def delete_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(MassageRecord).filter(
        MassageRecord.id == record_id,
        MassageRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    return {"message": "已删除"}


@router.get("/stats", response_model=MassageStats)
def get_stats(
    days: int = Query(90, description="统计天数"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    since = date.today() - timedelta(days=days)
    records = db.query(MassageRecord).filter(
        MassageRecord.user_id == current_user.id,
        MassageRecord.record_date >= since,
    ).all()

    if not records:
        return MassageStats()

    total_duration = sum(r.duration_minutes or 0 for r in records)
    total_cost = sum(r.price or 0 for r in records)
    ratings = [r.rating for r in records if r.rating]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    # 最常去的店
    locations = [r.location_name for r in records if r.location_name]
    fav_location = max(set(locations), key=locations.count) if locations else None

    # 最常选的师傅
    therapists = [r.therapist for r in records if r.therapist]
    fav_therapist = max(set(therapists), key=therapists.count) if therapists else None

    return MassageStats(
        total_sessions=len(records),
        total_duration_minutes=total_duration,
        total_cost=total_cost,
        avg_rating=round(avg_rating, 1) if avg_rating else None,
        favorite_location=fav_location,
        favorite_therapist=fav_therapist,
        last_session_date=max(r.record_date for r in records),
    )
