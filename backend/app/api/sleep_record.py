"""睡眠记录 API"""
from datetime import date, timedelta
from collections import Counter
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.sleep_record import SleepRecord
from app.schemas.sleep_record import (
    SleepRecordCreate, SleepRecordUpdate, SleepRecordResponse,
    SleepStats, SleepDailyTrend,
)

router = APIRouter(prefix="/sleep", tags=["睡眠记录"])


def _calc_duration(bedtime, wake_time) -> int:
    """计算睡眠时长（分钟）"""
    delta = wake_time - bedtime
    return max(0, int(delta.total_seconds() // 60))


@router.post("/records", response_model=SleepRecordResponse, summary="创建睡眠记录")
async def create_record(
    data: SleepRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = SleepRecord(
        user_id=current_user.id,
        total_duration_minutes=_calc_duration(data.bedtime, data.wake_time),
        **data.model_dump(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return SleepRecordResponse.model_validate(record)


@router.get("/records/me", response_model=List[SleepRecordResponse], summary="获取睡眠记录列表")
async def get_my_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    query = db.query(SleepRecord).filter(SleepRecord.user_id == current_user.id)
    if start_date:
        query = query.filter(SleepRecord.record_date >= start_date)
    if end_date:
        query = query.filter(SleepRecord.record_date <= end_date)
    records = query.order_by(desc(SleepRecord.record_date)).limit(limit).all()
    return [SleepRecordResponse.model_validate(r) for r in records]


@router.get("/records/me/today", response_model=Optional[SleepRecordResponse], summary="获取今日睡眠记录")
async def get_today_record(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today = date.today()
    record = db.query(SleepRecord).filter(
        SleepRecord.user_id == current_user.id,
        SleepRecord.record_date == today,
    ).order_by(desc(SleepRecord.created_at)).first()
    return SleepRecordResponse.model_validate(record) if record else None


@router.get("/records/{record_id}", response_model=SleepRecordResponse, summary="获取单条睡眠记录")
async def get_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(SleepRecord).filter(
        SleepRecord.id == record_id,
        SleepRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return SleepRecordResponse.model_validate(record)


@router.put("/records/{record_id}", response_model=SleepRecordResponse, summary="更新睡眠记录")
async def update_record(
    record_id: int,
    data: SleepRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(SleepRecord).filter(
        SleepRecord.id == record_id,
        SleepRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)

    # 如果时间有变化，重新计算时长
    if "bedtime" in update_data or "wake_time" in update_data:
        record.total_duration_minutes = _calc_duration(record.bedtime, record.wake_time)

    db.commit()
    db.refresh(record)
    return SleepRecordResponse.model_validate(record)


@router.delete("/records/{record_id}", summary="删除睡眠记录")
async def delete_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(SleepRecord).filter(
        SleepRecord.id == record_id,
        SleepRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    return {"message": "记录已删除"}


@router.get("/stats/me", response_model=SleepStats, summary="获取睡眠统计")
async def get_stats(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days - 1)
    records = db.query(SleepRecord).filter(
        SleepRecord.user_id == current_user.id,
        SleepRecord.record_date >= start_date,
    ).order_by(SleepRecord.record_date).all()

    if not records:
        return SleepStats()

    qualities = [r.sleep_quality for r in records]
    durations = [r.total_duration_minutes for r in records if r.total_duration_minutes]
    wake_counts = [r.wake_count for r in records if r.wake_count is not None]
    difficulties = [r.fall_asleep_difficulty for r in records if r.fall_asleep_difficulty]
    feelings = [r.morning_feeling for r in records if r.morning_feeling]
    dream_count = sum(1 for r in records if r.had_dream)

    # 平均入睡/醒来时间
    avg_bed_hour = avg_wake_hour = None
    bedtime_minutes = []
    wake_minutes = []
    for r in records:
        bm = r.bedtime.hour * 60 + r.bedtime.minute
        if bm < 720:  # 12:00之前算凌晨，+24h
            bm += 1440
        bedtime_minutes.append(bm)
        wake_minutes.append(r.wake_time.hour * 60 + r.wake_time.minute)

    avg_bedtime_str = None
    avg_wake_str = None
    if bedtime_minutes:
        avg_bm = int(sum(bedtime_minutes) / len(bedtime_minutes)) % 1440
        avg_bedtime_str = f"{avg_bm // 60:02d}:{avg_bm % 60:02d}"
    if wake_minutes:
        avg_wm = int(sum(wake_minutes) / len(wake_minutes))
        avg_wake_str = f"{avg_wm // 60:02d}:{avg_wm % 60:02d}"

    daily_trend = [
        SleepDailyTrend(
            date=r.record_date,
            sleep_quality=r.sleep_quality,
            duration_hours=round(r.total_duration_minutes / 60, 1) if r.total_duration_minutes else None,
            wake_count=r.wake_count,
            morning_feeling=r.morning_feeling,
        )
        for r in records
    ]

    return SleepStats(
        total_records=len(records),
        avg_sleep_quality=round(sum(qualities) / len(qualities), 1),
        avg_duration_hours=round(sum(durations) / len(durations) / 60, 1) if durations else None,
        avg_wake_count=round(sum(wake_counts) / len(wake_counts), 1) if wake_counts else None,
        avg_fall_asleep_difficulty=round(sum(difficulties) / len(difficulties), 1) if difficulties else None,
        avg_morning_feeling=round(sum(feelings) / len(feelings), 1) if feelings else None,
        dream_frequency=round(dream_count / len(records) * 100, 1),
        quality_distribution=dict(Counter(qualities)),
        daily_trend=daily_trend,
        avg_bedtime=avg_bedtime_str,
        avg_wake_time=avg_wake_str,
    )
