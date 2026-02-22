"""活动状态 API"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.activity_status import ActivityStatus
from app.schemas.activity_status import (
    ActivityStatusCreate, ActivityStatusUpdate, ActivityStatusResponse,
    ActivityStats, ActivityCategoryStats, ActivityTimelineItem,
)

router = APIRouter(prefix="/activity-status", tags=["活动状态"])


def _end_active_statuses(db: Session, user_id: int, end_time: datetime) -> None:
    """结束用户所有进行中的活动"""
    active = db.query(ActivityStatus).filter(
        ActivityStatus.user_id == user_id,
        ActivityStatus.is_active == True,
    ).all()
    for a in active:
        a.is_active = False
        a.actual_end_time = end_time


@router.post("/records", response_model=ActivityStatusResponse, summary="创建活动状态")
async def create_record(
    data: ActivityStatusCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    # 自动结束之前的活动
    _end_active_statuses(db, current_user.id, now)

    estimated_end = None
    if data.estimated_duration_minutes:
        estimated_end = now + timedelta(minutes=data.estimated_duration_minutes)

    record = ActivityStatus(
        user_id=current_user.id,
        status_text=data.status_text,
        category=data.category,
        start_time=now,
        estimated_duration_minutes=data.estimated_duration_minutes,
        estimated_end_time=estimated_end,
        is_active=True,
        notes=data.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ActivityStatusResponse.model_validate(record)


@router.get("/records/me/current", response_model=Optional[ActivityStatusResponse], summary="获取当前活动状态")
async def get_current_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ActivityStatus).filter(
        ActivityStatus.user_id == current_user.id,
        ActivityStatus.is_active == True,
    ).order_by(desc(ActivityStatus.start_time)).first()
    return ActivityStatusResponse.model_validate(record) if record else None


@router.put("/records/{record_id}/end", response_model=ActivityStatusResponse, summary="结束活动")
async def end_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ActivityStatus).filter(
        ActivityStatus.id == record_id,
        ActivityStatus.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not record.is_active:
        raise HTTPException(status_code=400, detail="该活动已结束")

    record.is_active = False
    record.actual_end_time = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return ActivityStatusResponse.model_validate(record)


@router.get("/records/me/today", response_model=List[ActivityTimelineItem], summary="今日活动时间线")
async def get_today_timeline(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today_start = datetime.combine(date.today(), datetime.min.time())
    records = db.query(ActivityStatus).filter(
        ActivityStatus.user_id == current_user.id,
        ActivityStatus.start_time >= today_start,
    ).order_by(ActivityStatus.start_time).all()

    now = datetime.now(timezone.utc)
    result = []
    for r in records:
        end = r.actual_end_time or (now if r.is_active else r.estimated_end_time)
        duration = None
        if end and r.start_time:
            delta = end - r.start_time
            duration = max(0, int(delta.total_seconds() // 60))
        result.append(ActivityTimelineItem(
            id=r.id,
            status_text=r.status_text,
            category=r.category,
            start_time=r.start_time,
            end_time=r.actual_end_time,
            duration_minutes=duration,
            is_active=r.is_active,
        ))
    return result


@router.get("/records/me", response_model=List[ActivityStatusResponse], summary="历史记录")
async def get_my_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    query = db.query(ActivityStatus).filter(ActivityStatus.user_id == current_user.id)
    if start_date:
        query = query.filter(ActivityStatus.start_time >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(ActivityStatus.start_time <= datetime.combine(end_date, datetime.max.time()))
    records = query.order_by(desc(ActivityStatus.start_time)).limit(limit).all()
    return [ActivityStatusResponse.model_validate(r) for r in records]


@router.get("/records/{record_id}", response_model=ActivityStatusResponse, summary="获取单条记录")
async def get_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ActivityStatus).filter(
        ActivityStatus.id == record_id,
        ActivityStatus.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return ActivityStatusResponse.model_validate(record)


@router.delete("/records/{record_id}", summary="删除记录")
async def delete_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(ActivityStatus).filter(
        ActivityStatus.id == record_id,
        ActivityStatus.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    return {"message": "记录已删除"}


@router.get("/stats/me", response_model=ActivityStats, summary="活动统计")
async def get_stats(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    start = datetime.combine(date.today() - timedelta(days=days - 1), datetime.min.time())
    records = db.query(ActivityStatus).filter(
        ActivityStatus.user_id == current_user.id,
        ActivityStatus.start_time >= start,
    ).order_by(ActivityStatus.start_time).all()

    if not records:
        return ActivityStats()

    now = datetime.now(timezone.utc)
    cat_minutes: dict = {}
    cat_count: dict = {}
    total_minutes = 0

    for r in records:
        end = r.actual_end_time or (now if r.is_active else r.estimated_end_time)
        duration = 0
        if end and r.start_time:
            delta = end - r.start_time
            duration = max(0, int(delta.total_seconds() // 60))

        cat = r.category or "other"
        cat_minutes[cat] = cat_minutes.get(cat, 0) + duration
        cat_count[cat] = cat_count.get(cat, 0) + 1
        total_minutes += duration

    distribution = []
    for cat, mins in sorted(cat_minutes.items(), key=lambda x: -x[1]):
        distribution.append(ActivityCategoryStats(
            category=cat,
            total_minutes=mins,
            count=cat_count[cat],
            percentage=round(mins / total_minutes * 100, 1) if total_minutes > 0 else 0,
        ))

    return ActivityStats(
        total_records=len(records),
        total_active_minutes=total_minutes,
        category_distribution=distribution,
    )
