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
    hrv_status: Optional[str] = None
    hrv_7day_avg: Optional[float] = None
    sleep_score: Optional[int] = None
    total_sleep_duration: Optional[int] = None
    deep_sleep_duration: Optional[int] = None
    rem_sleep_duration: Optional[int] = None
    light_sleep_duration: Optional[int] = None
    awake_duration: Optional[int] = None
    nap_duration: Optional[int] = None
    sleep_start_time: Optional[time] = None
    sleep_end_time: Optional[time] = None
    body_battery_charged: Optional[int] = None
    body_battery_drained: Optional[int] = None
    body_battery_most_charged: Optional[int] = None
    body_battery_lowest: Optional[int] = None
    stress_level: Optional[int] = None
    steps: Optional[int] = None
    calories_burned: Optional[int] = None
    active_calories: Optional[int] = None
    bmr_calories: Optional[int] = None
    active_minutes: Optional[int] = None
    intensity_minutes_goal: Optional[int] = None
    moderate_intensity_minutes: Optional[int] = None
    vigorous_intensity_minutes: Optional[int] = None
    avg_respiration_awake: Optional[float] = None
    avg_respiration_sleep: Optional[float] = None
    lowest_respiration: Optional[float] = None
    highest_respiration: Optional[float] = None
    spo2_avg: Optional[float] = None
    spo2_min: Optional[float] = None
    spo2_max: Optional[float] = None
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    floors_climbed: Optional[int] = None
    floors_goal: Optional[int] = None
    distance_meters: Optional[float] = None


class GarminDataResponse(BaseModel):
    """Garmin数据响应"""
    id: int
    user_id: int
    record_date: date
    avg_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    min_heart_rate: Optional[int] = None
    resting_heart_rate: Optional[int] = None
    hrv: Optional[float] = None
    hrv_status: Optional[str] = None
    hrv_7day_avg: Optional[float] = None
    sleep_score: Optional[int] = None
    total_sleep_duration: Optional[int] = None
    deep_sleep_duration: Optional[int] = None
    rem_sleep_duration: Optional[int] = None
    light_sleep_duration: Optional[int] = None
    awake_duration: Optional[int] = None
    nap_duration: Optional[int] = None
    sleep_start_time: Optional[time] = None
    sleep_end_time: Optional[time] = None
    body_battery_charged: Optional[int] = None
    body_battery_drained: Optional[int] = None
    body_battery_most_charged: Optional[int] = None
    body_battery_lowest: Optional[int] = None
    stress_level: Optional[int] = None
    steps: Optional[int] = None
    calories_burned: Optional[int] = None
    active_calories: Optional[int] = None
    bmr_calories: Optional[int] = None
    active_minutes: Optional[int] = None
    intensity_minutes_goal: Optional[int] = None
    moderate_intensity_minutes: Optional[int] = None
    vigorous_intensity_minutes: Optional[int] = None
    avg_respiration_awake: Optional[float] = None
    avg_respiration_sleep: Optional[float] = None
    lowest_respiration: Optional[float] = None
    highest_respiration: Optional[float] = None
    spo2_avg: Optional[float] = None
    spo2_min: Optional[float] = None
    spo2_max: Optional[float] = None
    vo2max_running: Optional[float] = None
    vo2max_cycling: Optional[float] = None
    floors_climbed: Optional[int] = None
    floors_goal: Optional[int] = None
    distance_meters: Optional[float] = None
    
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

