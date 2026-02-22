"""排泄记录 API"""
from datetime import date, timedelta
from collections import defaultdict, Counter
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.excretion import ExcretionRecord
from app.schemas.excretion import (
    ExcretionRecordCreate, ExcretionRecordUpdate, ExcretionRecordResponse,
    ExcretionStats, ExcretionDailySummary,
)

router = APIRouter(prefix="/excretion", tags=["排泄记录"])


@router.post("/records", response_model=ExcretionRecordResponse, summary="创建排泄记录")
async def create_record(
    data: ExcretionRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = ExcretionRecord(
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ExcretionRecordResponse.model_validate(record)


@router.get("/records/me", response_model=List[ExcretionRecordResponse], summary="获取排泄记录列表")
async def get_my_records(
    type: Optional[str] = Query(None, pattern="^(bowel|urine)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    query = db.query(ExcretionRecord).filter(ExcretionRecord.user_id == current_user.id)
    if type:
        query = query.filter(ExcretionRecord.type == type)
    if start_date:
        query = query.filter(ExcretionRecord.record_date >= start_date)
    if end_date:
        query = query.filter(ExcretionRecord.record_date <= end_date)
    records = query.order_by(desc(ExcretionRecord.record_date), desc(ExcretionRecord.record_time)).limit(limit).all()
    return [ExcretionRecordResponse.model_validate(r) for r in records]


@router.get("/records/me/today", response_model=List[ExcretionRecordResponse], summary="获取今日排泄记录")
async def get_today_records(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today = date.today()
    records = db.query(ExcretionRecord).filter(
        ExcretionRecord.user_id == current_user.id,
        ExcretionRecord.record_date == today,
    ).order_by(desc(ExcretionRecord.record_time)).all()
    return [ExcretionRecordResponse.model_validate(r) for r in records]


@router.get("/records/{record_id}", response_model=ExcretionRecordResponse, summary="获取单条排泄记录")
async def get_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ExcretionRecord).filter(
        ExcretionRecord.id == record_id,
        ExcretionRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return ExcretionRecordResponse.model_validate(record)


@router.put("/records/{record_id}", response_model=ExcretionRecordResponse, summary="更新排泄记录")
async def update_record(
    record_id: int,
    data: ExcretionRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ExcretionRecord).filter(
        ExcretionRecord.id == record_id,
        ExcretionRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return ExcretionRecordResponse.model_validate(record)


@router.delete("/records/{record_id}", summary="删除排泄记录")
async def delete_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ExcretionRecord).filter(
        ExcretionRecord.id == record_id,
        ExcretionRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    return {"message": "记录已删除"}


@router.get("/stats/me", response_model=ExcretionStats, summary="获取排泄统计")
async def get_stats(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days - 1)
    records = db.query(ExcretionRecord).filter(
        ExcretionRecord.user_id == current_user.id,
        ExcretionRecord.record_date >= start_date,
    ).order_by(ExcretionRecord.record_date).all()

    if not records:
        return ExcretionStats()

    bowel_records = [r for r in records if r.type == "bowel"]
    urine_records = [r for r in records if r.type == "urine"]

    # 按日分组
    day_bowel = defaultdict(int)
    day_urine = defaultdict(int)
    for r in bowel_records:
        day_bowel[r.record_date] += 1
    for r in urine_records:
        day_urine[r.record_date] += 1

    all_dates = set(r.record_date for r in records)
    num_days = max(len(all_dates), 1)

    stool_types = [r.stool_type for r in bowel_records if r.stool_type]
    colors = [r.color for r in bowel_records if r.color]
    blood_count = sum(1 for r in bowel_records if r.blood_present)

    # 每日汇总
    daily = []
    for d in sorted(all_dates):
        day_records = [r for r in records if r.record_date == d]
        day_bowels = [r for r in day_records if r.type == "bowel"]
        day_st = [r.stool_type for r in day_bowels if r.stool_type]
        daily.append(ExcretionDailySummary(
            date=d,
            bowel_count=len([r for r in day_records if r.type == "bowel"]),
            urine_count=len([r for r in day_records if r.type == "urine"]),
            avg_stool_type=round(sum(day_st) / len(day_st), 1) if day_st else None,
            has_blood=any(r.blood_present for r in day_bowels),
            has_pain=any((r.pain_level or 0) > 0 for r in day_records),
        ))

    return ExcretionStats(
        total_records=len(records),
        bowel_count=len(bowel_records),
        urine_count=len(urine_records),
        avg_bowel_per_day=round(len(bowel_records) / num_days, 1),
        avg_urine_per_day=round(len(urine_records) / num_days, 1),
        avg_stool_type=round(sum(stool_types) / len(stool_types), 1) if stool_types else None,
        stool_type_distribution=dict(Counter(stool_types)),
        color_distribution=dict(Counter(colors)),
        blood_count=blood_count,
        daily_summary=daily,
    )
