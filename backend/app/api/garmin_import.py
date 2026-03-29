"""Garmin 数据批量导入 API — 供本地同步脚本推送数据"""
import logging
from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.daily_health import GarminData, WorkoutRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/garmin-import", tags=["garmin-import"])


class DailySummary(BaseModel):
    record_date: str
    steps: Optional[int] = None
    resting_heart_rate: Optional[int] = None
    avg_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    min_heart_rate: Optional[int] = None
    stress_level: Optional[int] = None
    body_battery_most_charged: Optional[int] = None
    body_battery_lowest: Optional[int] = None
    calories_burned: Optional[int] = None
    active_minutes: Optional[int] = None
    sleep_score: Optional[int] = None
    total_sleep_duration: Optional[int] = None
    deep_sleep_duration: Optional[int] = None
    rem_sleep_duration: Optional[int] = None
    light_sleep_duration: Optional[int] = None
    awake_duration: Optional[int] = None
    hrv: Optional[int] = None
    spo2_avg: Optional[float] = None
    spo2_min: Optional[float] = None
    spo2_max: Optional[float] = None
    moderate_intensity_minutes: Optional[int] = None
    vigorous_intensity_minutes: Optional[int] = None
    intensity_minutes_goal: Optional[int] = None
    lowest_respiration: Optional[float] = None
    highest_respiration: Optional[float] = None
    avg_respiration_awake: Optional[float] = None
    avg_respiration_sleep: Optional[float] = None


class ActivityData(BaseModel):
    garmin_activity_id: str
    workout_date: str
    start_time: Optional[str] = None
    workout_type: str = "other"
    workout_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    moving_duration_seconds: Optional[int] = None
    distance_meters: Optional[float] = None
    avg_speed_kmh: Optional[float] = None
    max_speed_kmh: Optional[float] = None
    avg_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    min_heart_rate: Optional[int] = None
    calories: Optional[int] = None
    steps: Optional[int] = None
    elevation_gain_meters: Optional[float] = None
    elevation_loss_meters: Optional[float] = None
    min_elevation_meters: Optional[float] = None
    max_elevation_meters: Optional[float] = None
    avg_pace_seconds_per_km: Optional[int] = None
    best_pace_seconds_per_km: Optional[int] = None
    avg_cadence: Optional[int] = None
    max_cadence: Optional[int] = None
    avg_stride_length_cm: Optional[float] = None
    hr_zone_1_seconds: Optional[int] = None
    hr_zone_2_seconds: Optional[int] = None
    hr_zone_3_seconds: Optional[int] = None
    hr_zone_4_seconds: Optional[int] = None
    hr_zone_5_seconds: Optional[int] = None
    training_effect_aerobic: Optional[float] = None
    training_effect_anaerobic: Optional[float] = None
    vo2max: Optional[float] = None
    training_load: Optional[int] = None
    # JSON 时间序列数据（字符串格式）
    heart_rate_data: Optional[str] = None   # [{"time":0,"hr":120},...]
    pace_data: Optional[str] = None         # [{"time":0,"pace":360},...]
    elevation_data: Optional[str] = None    # [{"distance":0,"elevation":100},...]
    route_data: Optional[str] = None        # [{"lat":39.9,"lng":116.4,"ele":100,"time":0},...]
    lap_data: Optional[str] = None          # [{"lap":1,"distance":1000,"duration":300,...},...]


class GarminImportRequest(BaseModel):
    dailies: List[DailySummary] = []
    activities: List[ActivityData] = []


@router.post("/bulk", summary="批量导入 Garmin 数据")
async def bulk_import(
    req: GarminImportRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """本地同步脚本调用此接口推送 Garmin 数据"""
    daily_imported = daily_updated = 0
    activity_imported = activity_skipped = 0

    # 导入每日汇总
    for d in req.dailies:
        existing = db.query(GarminData).filter(
            GarminData.user_id == current_user.id,
            GarminData.record_date == d.record_date,
        ).first()

        if existing:
            for field in d.model_fields_set - {"record_date"}:
                val = getattr(d, field)
                if val is not None:
                    setattr(existing, field, val)
            daily_updated += 1
        else:
            record = GarminData(user_id=current_user.id, **d.model_dump(exclude_none=True))
            db.add(record)
            daily_imported += 1

    # 导入运动记录（upsert：已存在则更新，不存在则新建）
    activity_updated = 0
    for a in req.activities:
        existing = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == current_user.id,
            WorkoutRecord.external_id == a.garmin_activity_id,
        ).first()

        data = a.model_dump(exclude_none=True)
        data["external_id"] = data.pop("garmin_activity_id")  # 映射字段名

        if existing:
            for field, val in data.items():
                if val is not None and field not in ("workout_date", "external_id"):
                    setattr(existing, field, val)
            activity_updated += 1
        else:
            record = WorkoutRecord(
                user_id=current_user.id,
                source="garmin_cookie_sync",
                **data,
            )
            db.add(record)
            activity_imported += 1

    db.commit()

    return {
        "success": True,
        "daily_imported": daily_imported,
        "daily_updated": daily_updated,
        "activity_imported": activity_imported,
        "activity_updated": activity_updated,
        "activity_skipped": activity_skipped,
    }
