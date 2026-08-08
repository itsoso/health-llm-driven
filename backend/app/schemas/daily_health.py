"""日常健康记录Schema"""
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import date, datetime, time
from typing import Optional, Any, Dict


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
    body_battery_current: Optional[int] = None
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

    # P1a: Training Readiness / Status
    training_readiness_score: Optional[int] = None
    training_readiness_level: Optional[str] = None
    training_readiness_factors: Optional[Dict[str, Any]] = None
    training_status: Optional[str] = None
    training_status_feedback: Optional[str] = None
    acute_load: Optional[float] = None
    load_ratio: Optional[float] = None

    # P1a: 其他指标
    endurance_score: Optional[int] = None
    hill_score: Optional[int] = None
    race_predictions: Optional[Dict[str, Any]] = None
    hydration_ml: Optional[int] = None
    vo2max_fitness_age: Optional[int] = None


class _CoerceIntMixin:
    """自动将 float 字段截断为 int（解决 SQLite 不强制类型的问题）"""
    @field_validator("*", mode="before")
    @classmethod
    def coerce_float_to_int(cls, v, info):
        field = cls.model_fields.get(info.field_name)
        if field and field.annotation in (Optional[int], int) and isinstance(v, float):
            return int(v)
        return v


class GarminDataResponse(_CoerceIntMixin, BaseModel):
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
    body_battery_current: Optional[int] = None
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

    # P1a: Training Readiness / Status
    training_readiness_score: Optional[int] = None
    training_readiness_level: Optional[str] = None
    training_readiness_factors: Optional[Dict[str, Any]] = None
    training_status: Optional[str] = None
    training_status_feedback: Optional[str] = None
    acute_load: Optional[float] = None
    load_ratio: Optional[float] = None

    # P1a: 其他指标
    endurance_score: Optional[int] = None
    hill_score: Optional[int] = None
    race_predictions: Optional[Dict[str, Any]] = None
    hydration_ml: Optional[int] = None
    vo2max_fitness_age: Optional[int] = None

    # 多源:数据来源 (garmin / apple-watch / ringconn / oura / withings-app / unknown)
    data_source: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExerciseRecordCreate(BaseModel):
    """创建锻炼记录"""
    model_config = ConfigDict(allow_inf_nan=False)

    record_date: date
    exercise_type: str
    duration: Optional[int] = None              # 分钟
    duration_seconds: Optional[int] = None      # 秒 (倒立等亚分钟精度场景)
    intensity: Optional[str] = None
    calories_burned: Optional[int] = None
    reps: Optional[int] = None
    sets: Optional[int] = None
    distance: Optional[float] = None
    notes: Optional[str] = None


class ExerciseRecordUpdate(BaseModel):
    """更新锻炼记录"""
    model_config = ConfigDict(allow_inf_nan=False)

    record_date: Optional[date] = None
    exercise_type: Optional[str] = None
    duration: Optional[int] = None
    duration_seconds: Optional[int] = None
    intensity: Optional[str] = None
    calories_burned: Optional[int] = None
    reps: Optional[int] = None
    sets: Optional[int] = None
    distance: Optional[float] = None
    notes: Optional[str] = None


class ExerciseRecordResponse(BaseModel):
    """锻炼记录响应"""
    id: int
    user_id: int
    record_date: date
    exercise_type: str
    duration: Optional[int] = None
    duration_seconds: Optional[int] = None
    intensity: Optional[str] = None
    calories_burned: Optional[int] = None
    reps: Optional[int] = None
    sets: Optional[int] = None
    distance: Optional[float] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    # 成品话术: 弱模型常把整坨响应吐给用户, skill 统一只输出这个字段 (对齐 DietRecordResponse)
    display_message: str = ""

    model_config = ConfigDict(from_attributes=True)

    def model_post_init(self, __context: Any) -> None:
        parts = []
        if self.sets and self.sets > 1 and self.reps is not None:
            parts.append(f"{self.sets} 组 × {self.reps} 个")
        elif self.reps is not None:
            parts.append(f"{self.reps} 个")
        elif self.duration_seconds is not None:
            parts.append(f"{self.duration_seconds} 秒")
        elif self.duration is not None:
            parts.append(f"{self.duration} 分钟")
        if self.distance is not None:
            parts.append(f"{self.distance:g} 公里")
        msg = f"✅ 已记录{self.exercise_type}"
        if parts:
            msg += " " + "，".join(parts)
        object.__setattr__(self, "display_message", msg)


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
