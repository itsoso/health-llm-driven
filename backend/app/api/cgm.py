"""
CGM API 端点。

- POST /api/v1/cgm/readings             单条/批量录入
- GET  /api/v1/cgm/readings/latest      最近一条
- GET  /api/v1/cgm/readings/summary     24 小时摘要
- GET  /api/v1/cgm/readings             时段查询（分页）
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.cgm_reading import CgmReading
from app.models.user import User
from app.services.cgm import CgmService

router = APIRouter(prefix="/cgm", tags=["cgm"])


class CgmReadingIn(BaseModel):
    measured_at: datetime
    glucose_mg_dl: float = Field(..., ge=20, le=600)
    trend_arrow: Optional[str] = None
    trend_rate: Optional[float] = None
    source: str = "manual"
    device_serial: Optional[str] = None
    raw_id: Optional[str] = None
    notes: Optional[str] = None


class CgmReadingOut(BaseModel):
    id: int
    measured_at: datetime
    glucose_mg_dl: float
    glucose_mmol_l: Optional[float]
    trend_arrow: Optional[str]
    source: str

    class Config:
        from_attributes = True


class CgmBatchIn(BaseModel):
    readings: List[CgmReadingIn]


@router.post("/readings", response_model=CgmReadingOut)
def create_reading(
    body: CgmReadingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """录入一条 CGM 读数。"""
    svc = CgmService()
    reading = svc.ingest_reading(
        db=db,
        user_id=current_user.id,
        measured_at=body.measured_at,
        glucose_mg_dl=body.glucose_mg_dl,
        source=body.source,
        trend_arrow=body.trend_arrow,
        trend_rate=body.trend_rate,
        device_serial=body.device_serial,
        raw_id=body.raw_id,
        notes=body.notes,
    )
    return CgmReadingOut(
        id=reading.id,
        measured_at=reading.measured_at,
        glucose_mg_dl=reading.glucose_mg_dl,
        glucose_mmol_l=reading.glucose_mmol_l,
        trend_arrow=reading.trend_arrow,
        source=reading.source,
    )


@router.post("/readings/batch")
def create_readings_batch(
    body: CgmBatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """批量录入（幂等 by raw_id）。"""
    svc = CgmService()
    result = svc.ingest_batch(db, current_user.id, [r.model_dump() for r in body.readings])
    return result


@router.get("/readings/latest", response_model=Optional[CgmReadingOut])
def get_latest_reading(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    svc = CgmService()
    reading = svc.get_latest_reading(db, current_user.id)
    if not reading:
        return None
    return CgmReadingOut(
        id=reading.id,
        measured_at=reading.measured_at,
        glucose_mg_dl=reading.glucose_mg_dl,
        glucose_mmol_l=reading.glucose_mmol_l,
        trend_arrow=reading.trend_arrow,
        source=reading.source,
    )


@router.get("/readings/summary")
def get_summary(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """获取指定小时数的 CGM 摘要（默认 24h）。"""
    svc = CgmService()
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    summary = svc.get_range_summary(db, current_user.id, start, end)
    return {
        "hours": hours,
        "start": summary.start.isoformat(),
        "end": summary.end.isoformat(),
        "count": summary.count,
        "mean_mg_dl": summary.mean_mg_dl,
        "std_mg_dl": summary.std_mg_dl,
        "cv_pct": summary.cv_pct,
        "gmi_estimated_a1c": summary.gmi,
        "time_in_range_70_180_pct": summary.tir_pct,
        "time_below_70_pct": summary.time_below_pct,
        "time_above_180_pct": summary.time_above_pct,
        "severe_low_count_below_54": summary.severe_low_count,
        "severe_high_count_above_250": summary.severe_high_count,
        "latest_mg_dl": summary.latest_mg_dl,
        "latest_trend_arrow": summary.latest_trend_arrow,
    }


@router.get("/readings")
def list_readings(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """列出指定小时内的读数（按时间倒序）。"""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    rows = (
        db.query(CgmReading)
        .filter(
            CgmReading.user_id == current_user.id,
            CgmReading.measured_at >= start,
            CgmReading.measured_at <= end,
        )
        .order_by(CgmReading.measured_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "measured_at": r.measured_at.isoformat(),
            "glucose_mg_dl": r.glucose_mg_dl,
            "glucose_mmol_l": r.glucose_mmol_l,
            "trend_arrow": r.trend_arrow,
            "source": r.source,
        }
        for r in rows
    ]
