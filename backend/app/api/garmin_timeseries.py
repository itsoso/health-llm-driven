"""Garmin 时间序列与训练就绪度 API（P1a 只读）。

对外暴露 respiration / hrv / stress / devices / training_readiness / hr_zones 等数据。
分析逻辑留给 P1b 的 nocturnal_spo2_analyzer。
"""
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.models.user import User
from app.models.daily_health import GarminData, HeartRateSample, SpO2Sample, SleepLevelInterval
from app.models.garmin_timeseries import RespirationSample, HrvReading, StressSample
from app.models.workout_hr_zone import WorkoutHrZone
from app.models.garmin_device import GarminDevice
from app.models.weight import WeightRecord
from app.api.deps import get_current_user_required

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic 响应 schemas
# ---------------------------------------------------------------------------

class _TsPoint(BaseModel):
    """时间序列一个点 (HH:MM + 数值)。"""
    sample_time: time
    value: Optional[float] = None
    epoch_ms: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class NightlyTimeseriesResponse(BaseModel):
    """一夜/一天的多条时序对齐。value_str 仅对 sleep_stage 有意义。"""
    record_date: date
    metrics: Dict[str, List[_TsPoint]]   # { "spo2": [...], "hr": [...], ... }
    counts: Dict[str, int]                # 每条时序点数
    sleep_stages: List[Dict[str, Any]]    # [{start_ms, end_ms, level}]


class TrainingReadinessResponse(BaseModel):
    record_date: date
    training_readiness_score: Optional[int] = None
    training_readiness_level: Optional[str] = None
    training_readiness_factors: Optional[Dict[str, Any]] = None
    training_status: Optional[str] = None
    training_status_feedback: Optional[str] = None
    acute_load: Optional[float] = None
    load_ratio: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class WorkoutHrZoneResponse(BaseModel):
    zone_index: int
    zone_name: Optional[str] = None
    lower_bpm: Optional[int] = None
    upper_bpm: Optional[int] = None
    seconds_in_zone: int
    model_config = ConfigDict(from_attributes=True)


class GarminDeviceResponse(BaseModel):
    device_id: str
    model: Optional[str] = None
    display_name: Optional[str] = None
    last_sync_time: Optional[datetime] = None
    last_used_time: Optional[datetime] = None
    battery_level: Optional[int] = None
    battery_status: Optional[str] = None
    firmware_version: Optional[str] = None
    is_primary: bool = False
    hours_since_last_sync: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class BodyCompositionResponse(BaseModel):
    record_date: date
    weight: Optional[float] = None
    body_fat_percentage: Optional[float] = None
    muscle_mass_kg: Optional[float] = None
    bone_mass_kg: Optional[float] = None
    water_percentage: Optional[float] = None
    visceral_fat: Optional[int] = None
    bmi: Optional[float] = None
    metabolic_age: Optional[int] = None
    source: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/nightly/me/{target_date}", response_model=NightlyTimeseriesResponse)
def get_nightly_timeseries(
    target_date: date,
    metrics: str = Query(
        "spo2,hr,respiration,hrv,stress,sleep_stage",
        description="逗号分隔指标名：spo2,hr,respiration,hrv,stress,sleep_stage",
    ),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> NightlyTimeseriesResponse:
    """返回当日多条时序，供前端画对齐曲线。"""
    wanted = {m.strip() for m in metrics.split(",") if m.strip()}
    out: Dict[str, List[_TsPoint]] = {}
    counts: Dict[str, int] = {}

    if "spo2" in wanted:
        rows = db.query(SpO2Sample).filter(
            SpO2Sample.user_id == current_user.id,
            SpO2Sample.record_date == target_date,
        ).order_by(SpO2Sample.sample_time).all()
        out["spo2"] = [
            _TsPoint(sample_time=r.sample_time, value=r.spo2_value, epoch_ms=r.epoch_ms)
            for r in rows
        ]
        counts["spo2"] = len(rows)

    if "hr" in wanted:
        rows = db.query(HeartRateSample).filter(
            HeartRateSample.user_id == current_user.id,
            HeartRateSample.record_date == target_date,
        ).order_by(HeartRateSample.sample_time).all()
        out["hr"] = [_TsPoint(sample_time=r.sample_time, value=r.heart_rate) for r in rows]
        counts["hr"] = len(rows)

    if "respiration" in wanted:
        rows = db.query(RespirationSample).filter(
            RespirationSample.user_id == current_user.id,
            RespirationSample.record_date == target_date,
        ).order_by(RespirationSample.sample_time).all()
        out["respiration"] = [
            _TsPoint(sample_time=r.sample_time, value=r.respiration_rate, epoch_ms=r.epoch_ms)
            for r in rows
        ]
        counts["respiration"] = len(rows)

    if "hrv" in wanted:
        rows = db.query(HrvReading).filter(
            HrvReading.user_id == current_user.id,
            HrvReading.record_date == target_date,
        ).order_by(HrvReading.reading_time).all()
        out["hrv"] = [
            _TsPoint(sample_time=r.reading_time, value=r.hrv_value, epoch_ms=r.epoch_ms)
            for r in rows
        ]
        counts["hrv"] = len(rows)

    if "stress" in wanted:
        rows = db.query(StressSample).filter(
            StressSample.user_id == current_user.id,
            StressSample.record_date == target_date,
        ).order_by(StressSample.sample_time).all()
        out["stress"] = [
            _TsPoint(sample_time=r.sample_time, value=r.stress_value, epoch_ms=r.epoch_ms)
            for r in rows
        ]
        counts["stress"] = len(rows)

    sleep_stages_out: List[Dict[str, Any]] = []
    if "sleep_stage" in wanted:
        rows = db.query(SleepLevelInterval).filter(
            SleepLevelInterval.user_id == current_user.id,
            SleepLevelInterval.record_date == target_date,
        ).order_by(SleepLevelInterval.start_epoch_ms).all()
        sleep_stages_out = [
            {
                "start_ms": r.start_epoch_ms,
                "end_ms": r.end_epoch_ms,
                "level": r.activity_level,
            }
            for r in rows
        ]
        counts["sleep_stage"] = len(rows)

    return NightlyTimeseriesResponse(
        record_date=target_date,
        metrics=out,
        counts=counts,
        sleep_stages=sleep_stages_out,
    )


@router.get("/training/me/trend", response_model=List[TrainingReadinessResponse])
def get_training_readiness_trend(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> List[TrainingReadinessResponse]:
    """返回最近 N 天 Training Readiness 序列。"""
    start = date.today() - timedelta(days=days)
    rows = db.query(GarminData).filter(
        GarminData.user_id == current_user.id,
        GarminData.record_date >= start,
        GarminData.training_readiness_score.isnot(None),
    ).order_by(GarminData.record_date).all()
    return [
        TrainingReadinessResponse(
            record_date=r.record_date,
            training_readiness_score=r.training_readiness_score,
            training_readiness_level=r.training_readiness_level,
            training_readiness_factors=r.training_readiness_factors,
            training_status=r.training_status,
            training_status_feedback=r.training_status_feedback,
            acute_load=r.acute_load,
            load_ratio=r.load_ratio,
        )
        for r in rows
    ]


@router.get("/training/me/{target_date}", response_model=TrainingReadinessResponse)
def get_training_readiness(
    target_date: date,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> TrainingReadinessResponse:
    """返回当日 Garmin Training Readiness + Status。"""
    row = db.query(GarminData).filter(
        GarminData.user_id == current_user.id,
        GarminData.record_date == target_date,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"未找到 {target_date} 的 Garmin 数据")
    return TrainingReadinessResponse(
        record_date=target_date,
        training_readiness_score=row.training_readiness_score,
        training_readiness_level=row.training_readiness_level,
        training_readiness_factors=row.training_readiness_factors,
        training_status=row.training_status,
        training_status_feedback=row.training_status_feedback,
        acute_load=row.acute_load,
        load_ratio=row.load_ratio,
    )


@router.get("/body-composition/me", response_model=List[BodyCompositionResponse])
def get_body_composition_history(
    days: int = Query(90, ge=1, le=365),
    source: Optional[str] = Query(None, description="筛选来源，如 garmin_index / manual"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> List[BodyCompositionResponse]:
    """返回最近 N 天体成分（来自 weight_records，Garmin Index 或手动录入）。"""
    start = date.today() - timedelta(days=days)
    q = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id,
        WeightRecord.record_date >= start,
    )
    if source:
        q = q.filter(WeightRecord.source == source)
    rows = q.order_by(WeightRecord.record_date).all()
    return [
        BodyCompositionResponse(
            record_date=r.record_date,
            weight=r.weight,
            body_fat_percentage=r.body_fat_percentage,
            muscle_mass_kg=r.muscle_mass_kg,
            bone_mass_kg=r.bone_mass_kg,
            water_percentage=r.water_percentage,
            visceral_fat=r.visceral_fat,
            bmi=r.bmi,
            metabolic_age=r.metabolic_age,
            source=r.source,
        )
        for r in rows
    ]


@router.get("/devices/me", response_model=List[GarminDeviceResponse])
def get_devices(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> List[GarminDeviceResponse]:
    """返回用户 Garmin 设备列表（含电量/最近同步）。"""
    rows = db.query(GarminDevice).filter(
        GarminDevice.user_id == current_user.id,
    ).order_by(GarminDevice.is_primary.desc(), GarminDevice.last_sync_time.desc().nullslast()).all()

    now = datetime.now()
    out: List[GarminDeviceResponse] = []
    for r in rows:
        hours_since = None
        if r.last_sync_time:
            try:
                last_naive = r.last_sync_time.replace(tzinfo=None) if r.last_sync_time.tzinfo else r.last_sync_time
                hours_since = (now - last_naive).total_seconds() / 3600
            except (AttributeError, TypeError):
                hours_since = None
        out.append(GarminDeviceResponse(
            device_id=r.device_id,
            model=r.model,
            display_name=r.display_name,
            last_sync_time=r.last_sync_time,
            last_used_time=r.last_used_time,
            battery_level=r.battery_level,
            battery_status=r.battery_status,
            firmware_version=r.firmware_version,
            is_primary=r.is_primary,
            hours_since_last_sync=hours_since,
        ))
    return out


@router.get("/workout/{workout_id}/hr-zones", response_model=List[WorkoutHrZoneResponse])
def get_workout_hr_zones(
    workout_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> List[WorkoutHrZoneResponse]:
    """单次训练的心率区间分布（Z1-Z5）。"""
    # 先校验 workout 属于当前用户
    from app.models.daily_health import WorkoutRecord  # lazy import 避免循环
    w = db.query(WorkoutRecord).filter(
        WorkoutRecord.id == workout_id,
        WorkoutRecord.user_id == current_user.id,
    ).first()
    if not w:
        raise HTTPException(status_code=404, detail="Workout not found")

    rows = db.query(WorkoutHrZone).filter(
        WorkoutHrZone.workout_id == workout_id,
    ).order_by(WorkoutHrZone.zone_index).all()
    return [WorkoutHrZoneResponse.model_validate(r) for r in rows]
