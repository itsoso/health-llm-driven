"""SpO2 血氧时间序列 API"""
from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.user import User
from app.models.daily_health import SpO2Sample, GarminData
from app.api.deps import get_current_user_required
from app.schemas.spo2 import (
    SpO2Point,
    SpO2NightSummary,
    SpO2NightlyResponse,
    SpO2TrendResponse,
)

router = APIRouter()


def _compute_desaturation_events(values: List[int]) -> int:
    if len(values) < 2:
        return 0
    events = 0
    baseline = values[0]
    in_desat = False
    for v in values[1:]:
        if not in_desat and baseline - v >= 3:
            events += 1
            in_desat = True
        elif v >= baseline - 1:
            in_desat = False
            baseline = v
        if v > baseline:
            baseline = v
    return events


def _build_night_summary(
    record_date: date,
    samples: List[SpO2Sample],
    sleep_hours: Optional[float] = None,
) -> SpO2NightSummary:
    if not samples:
        return SpO2NightSummary(record_date=record_date)

    values = [s.spo2_value for s in samples]
    avg_val = sum(values) / len(values)
    below_90 = sum(1 for v in values if v < 90)
    desat = _compute_desaturation_events(values)

    hours = sleep_hours
    if hours is None and len(values) > 1:
        hours = len(values) / 60.0

    odi = round(desat / hours, 1) if hours and hours > 0 else None

    return SpO2NightSummary(
        record_date=record_date,
        avg_spo2=round(avg_val, 1),
        min_spo2=min(values),
        max_spo2=max(values),
        below_90_count=below_90,
        desaturation_events=desat,
        odi=odi,
        data_points=len(values),
    )


def _get_sleep_times(db: Session, user_id: int, record_date: date):
    garmin = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id, GarminData.record_date == record_date)
        .first()
    )
    if not garmin:
        return None, None, None
    start = garmin.sleep_start_time.strftime("%H:%M") if garmin.sleep_start_time else None
    end = garmin.sleep_end_time.strftime("%H:%M") if garmin.sleep_end_time else None
    duration_h = garmin.total_sleep_duration / 60.0 if garmin.total_sleep_duration else None
    return start, end, duration_h


@router.get("/me/nightly/{record_date}", response_model=SpO2NightlyResponse)
def get_nightly_spo2(
    record_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    samples = (
        db.query(SpO2Sample)
        .filter(
            SpO2Sample.user_id == current_user.id,
            SpO2Sample.record_date == record_date,
        )
        .order_by(SpO2Sample.epoch_ms.asc())
        .all()
    )

    sleep_start, sleep_end, sleep_hours = _get_sleep_times(db, current_user.id, record_date)
    summary = _build_night_summary(record_date, samples, sleep_hours)

    timeline = [
        SpO2Point(
            timestamp=s.epoch_ms or 0,
            time=s.sample_time.strftime("%H:%M"),
            value=s.spo2_value,
        )
        for s in samples
    ]

    return SpO2NightlyResponse(
        record_date=record_date,
        summary=summary,
        timeline=timeline,
        sleep_start=sleep_start,
        sleep_end=sleep_end,
    )


@router.get("/me/latest-night", response_model=SpO2NightlyResponse)
def get_latest_night_spo2(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    latest = (
        db.query(SpO2Sample.record_date)
        .filter(SpO2Sample.user_id == current_user.id)
        .order_by(desc(SpO2Sample.record_date))
        .first()
    )
    if not latest:
        raise HTTPException(status_code=404, detail="暂无血氧采样数据")
    return get_nightly_spo2(latest[0], current_user, db)


@router.get("/me/trend", response_model=SpO2TrendResponse)
def get_spo2_trend(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    dates_with_data = (
        db.query(SpO2Sample.record_date)
        .filter(
            SpO2Sample.user_id == current_user.id,
            SpO2Sample.record_date >= start_date,
            SpO2Sample.record_date <= end_date,
        )
        .distinct()
        .order_by(SpO2Sample.record_date)
        .all()
    )

    daily: List[SpO2NightSummary] = []
    for (rd,) in dates_with_data:
        samples = (
            db.query(SpO2Sample)
            .filter(
                SpO2Sample.user_id == current_user.id,
                SpO2Sample.record_date == rd,
            )
            .order_by(SpO2Sample.epoch_ms.asc())
            .all()
        )
        _, _, sleep_hours = _get_sleep_times(db, current_user.id, rd)
        daily.append(_build_night_summary(rd, samples, sleep_hours))

    summaries_with_avg = [d for d in daily if d.avg_spo2 is not None]
    summaries_with_odi = [d for d in daily if d.odi is not None]

    return SpO2TrendResponse(
        days=days,
        daily_data=daily,
        avg_nightly_spo2=(
            round(sum(d.avg_spo2 for d in summaries_with_avg) / len(summaries_with_avg), 1)
            if summaries_with_avg
            else None
        ),
        avg_odi=(
            round(sum(d.odi for d in summaries_with_odi) / len(summaries_with_odi), 1)
            if summaries_with_odi
            else None
        ),
        nights_with_odi_above_5=sum(1 for d in daily if d.odi is not None and d.odi >= 5),
    )
