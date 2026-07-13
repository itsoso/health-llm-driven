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
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.cgm_reading import CgmReading
from app.models.user import User
from app.services.cgm import CgmService

router = APIRouter(prefix="/cgm", tags=["cgm"])


def _invalidate_twin(user_id: int) -> None:
    """Fail-soft twin-cache invalidation after a write (rank7: also drops pregen)."""
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001 — a Redis error must never fail the write
        pass


# 与 models/cgm_reading.py 的 mmol property 及 rules/cgm.py 同口径(round-trip 自洽)
_MMOL_TO_MGDL = 18.0


class CgmReadingIn(BaseModel):
    # 血糖可传 mg/dL 或 mmol/L(中国默认 mmol)—— 二选一,只给 mmol 时自动换算。
    # measured_at 在此**不默认**:留 None,单条端点 create_reading 才补 now;batch 缺时间须被
    # service 跳过(若在此默认 now 会把设备导入缺时间的脏数据全标当前 → 见安全评审阻断2)。
    measured_at: Optional[datetime] = None
    glucose_mg_dl: Optional[float] = Field(None, ge=20, le=600)
    glucose_mmol_l: Optional[float] = Field(None, ge=1.0, le=33.0)
    trend_arrow: Optional[str] = None
    trend_rate: Optional[float] = None
    source: str = "manual"
    device_serial: Optional[str] = None
    raw_id: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _normalize_glucose(self):
        if self.glucose_mg_dl is None:
            if self.glucose_mmol_l is None:
                raise ValueError("必须提供 glucose_mg_dl 或 glucose_mmol_l 其一")
            self.glucose_mg_dl = round(self.glucose_mmol_l * _MMOL_TO_MGDL, 1)
        # 换算后复检值域(field 的 ge/le 在赋值前已跑过,这里兜住 mmol→mg/dL 的越界,
        # 否则 mmol 1.0→18mg/dL 会绕过 mg_dL 的 ≥20 下限喂给低血糖 CRITICAL 规则)
        if not (20 <= self.glucose_mg_dl <= 600):
            raise ValueError("血糖换算后超出合理范围(20–600 mg/dL,约 1.1–33.3 mmol/L)")
        return self


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
    # 单条手动录入:缺 measured_at 默认现在(batch 不走这,缺时间由 service 跳过)。
    # ⚠️ 补录历史血糖须由调用方显式传 measured_at,否则旧值被当「最新」误触急性告警。
    reading = svc.ingest_reading(
        db=db,
        user_id=current_user.id,
        measured_at=body.measured_at or datetime.now(timezone.utc),
        glucose_mg_dl=body.glucose_mg_dl,
        source=body.source,
        trend_arrow=body.trend_arrow,
        trend_rate=body.trend_rate,
        device_serial=body.device_serial,
        raw_id=body.raw_id,
        notes=body.notes,
    )
    _invalidate_twin(current_user.id)
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
    _invalidate_twin(current_user.id)
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
