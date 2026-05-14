"""腰围追踪 API."""

from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.models.waist import WaistRecord
from app.schemas.waist import WaistRecordInput, WaistRecordResponse, WaistRecordUpdate

router = APIRouter()


def _invalidate_twin(user_id: int) -> None:
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:
        pass


@router.post("/records", response_model=WaistRecordResponse)
def create_waist_record(
    record: WaistRecordInput,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建或更新当天腰围记录."""
    existing = (
        db.query(WaistRecord)
        .filter(
            WaistRecord.user_id == current_user.id,
            WaistRecord.record_date == record.record_date,
        )
        .first()
    )
    if existing:
        existing.waist_cm = record.waist_cm
        existing.source = record.source or existing.source
        existing.notes = record.notes
        db.commit()
        db.refresh(existing)
        _invalidate_twin(current_user.id)
        return existing

    db_record = WaistRecord(
        user_id=current_user.id,
        record_date=record.record_date,
        waist_cm=record.waist_cm,
        source=record.source or "manual",
        notes=record.notes,
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    _invalidate_twin(current_user.id)
    return db_record


@router.get("/records/me", response_model=List[WaistRecordResponse])
def get_my_waist_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户腰围记录."""
    query = db.query(WaistRecord).filter(WaistRecord.user_id == current_user.id)
    if start_date:
        query = query.filter(WaistRecord.record_date >= start_date)
    if end_date:
        query = query.filter(WaistRecord.record_date <= end_date)
    return query.order_by(desc(WaistRecord.record_date)).limit(limit).all()


@router.get("/records/me/latest", response_model=Optional[WaistRecordResponse])
def get_my_latest_waist(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取最新腰围记录."""
    return (
        db.query(WaistRecord)
        .filter(WaistRecord.user_id == current_user.id)
        .order_by(desc(WaistRecord.record_date))
        .first()
    )


@router.get("/records/me/stats")
def get_my_waist_stats(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取腰围统计."""
    start = date.today() - timedelta(days=days)
    records = (
        db.query(WaistRecord)
        .filter(WaistRecord.user_id == current_user.id, WaistRecord.record_date >= start)
        .order_by(desc(WaistRecord.record_date))
        .all()
    )
    if not records:
        return {"total_records": 0}
    values = [r.waist_cm for r in records if r.waist_cm is not None]
    change = round(records[0].waist_cm - records[-1].waist_cm, 1) if len(records) >= 2 else None
    return {
        "current_waist_cm": records[0].waist_cm,
        "average_waist_cm": round(sum(values) / len(values), 1) if values else None,
        "waist_change_cm": change,
        "total_records": len(records),
    }


@router.put("/records/{record_id}", response_model=WaistRecordResponse)
def update_waist_record(
    record_id: int,
    update: WaistRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新自己的腰围记录."""
    record = (
        db.query(WaistRecord)
        .filter(WaistRecord.id == record_id, WaistRecord.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    _invalidate_twin(current_user.id)
    return record


@router.delete("/records/{record_id}")
def delete_waist_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除自己的腰围记录."""
    record = (
        db.query(WaistRecord)
        .filter(WaistRecord.id == record_id, WaistRecord.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    _invalidate_twin(current_user.id)
    return {"message": "删除成功"}
