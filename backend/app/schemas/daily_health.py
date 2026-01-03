"""日常健康记录Schema"""
from pydantic import BaseModel
from datetime import date, time
from typing import Optional


class GarminDataCreate(BaseModel):
    """创建Garmin数据"""
    user_id: int
    record_date: date
    avg_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    min_heart_rate: Optional[int] = None
    resting_heart_rate: Optional[int] = None
    hrv: Optional[float] = None
    sleep_score: Optional[int] = None
    total_sleep_duration: Optional[int] = None
    deep_sleep_duration: Optional[int] = None
    rem_sleep_duration: Optional[int] = None
    light_sleep_duration: Optional[int] = None
    awake_duration: Optional[int] = None
    sleep_start_time: Optional[time] = None
    sleep_end_time: Optional[time] = None
    body_battery_charged: Optional[int] = None
    body_battery_drained: Optional[int] = None
    body_battery_most_charged: Optional[int] = None
    body_battery_lowest: Optional[int] = None
    stress_level: Optional[int] = None
    steps: Optional[int] = None
    calories_burned: Optional[int] = None
    active_minutes: Optional[int] = None


class GarminDataResponse(BaseModel):
    """Garmin数据响应"""
    id: int
    user_id: int
    record_date: date
    avg_heart_rate: Optional[int]
    max_heart_rate: Optional[int]
    min_heart_rate: Optional[int]
    resting_heart_rate: Optional[int]
    hrv: Optional[float]
    sleep_score: Optional[int]
    total_sleep_duration: Optional[int]
    deep_sleep_duration: Optional[int]
    rem_sleep_duration: Optional[int]
    light_sleep_duration: Optional[int]
    awake_duration: Optional[int]
    sleep_start_time: Optional[time]
    sleep_end_time: Optional[time]
    body_battery_charged: Optional[int]
    body_battery_drained: Optional[int]
    body_battery_most_charged: Optional[int]
    body_battery_lowest: Optional[int]
    stress_level: Optional[int]
    steps: Optional[int]
    calories_burned: Optional[int]
    active_minutes: Optional[int]
    
    class Config:
        from_attributes = True


class ExerciseRecordCreate(BaseModel):
    """创建锻炼记录"""
    user_id: int
    record_date: date
    exercise_type: str
    duration: Optional[int] = None
    intensity: Optional[str] = None
    calories_burned: Optional[int] = None
    distance: Optional[float] = None
    notes: Optional[str] = None


class DietRecordCreate(BaseModel):
    """创建饮食记录"""
    user_id: int
    record_date: date
    meal_type: str
    meal_time: Optional[time] = None
    food_name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None
    notes: Optional[str] = None


class WaterIntakeCreate(BaseModel):
    """创建饮水记录"""
    user_id: int
    record_date: date
    intake_time: Optional[time] = None
    amount: float
    notes: Optional[str] = None


class SupplementIntakeCreate(BaseModel):
    """创建补剂记录"""
    user_id: int
    record_date: date
    supplement_name: str
    intake_time: Optional[time] = None
    dosage: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None


class OutdoorActivityCreate(BaseModel):
    """创建户外活动记录"""
    user_id: int
    record_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    duration: Optional[int] = None
    activity_type: Optional[str] = None
    uv_index: Optional[float] = None
    notes: Optional[str] = None

