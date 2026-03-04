"""健康报告 API Schemas"""
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ExerciseSummary(BaseModel):
    """运动数据摘要"""
    total_steps: int = 0
    avg_daily_steps: int = 0
    total_active_minutes: int = 0
    total_calories_burned: float = 0
    workout_count: int = 0
    workout_types: Dict[str, int] = Field(default_factory=dict)
    avg_heart_rate: Optional[float] = None
    max_heart_rate: Optional[int] = None


class DietSummary(BaseModel):
    """饮食数据摘要"""
    avg_daily_calories: Optional[float] = None
    avg_daily_protein: Optional[float] = None
    avg_daily_carbs: Optional[float] = None
    avg_daily_fat: Optional[float] = None
    meal_count: int = 0
    record_days: int = 0


class SleepSummary(BaseModel):
    """睡眠数据摘要"""
    avg_sleep_duration: Optional[float] = None
    avg_sleep_score: Optional[float] = None
    avg_deep_sleep: Optional[float] = None
    avg_rem_sleep: Optional[float] = None
    best_sleep_date: Optional[date] = None
    worst_sleep_date: Optional[date] = None


class WeightSummary(BaseModel):
    """体重变化摘要"""
    start_weight: Optional[float] = None
    end_weight: Optional[float] = None
    weight_change: Optional[float] = None
    min_weight: Optional[float] = None
    max_weight: Optional[float] = None
    record_count: int = 0


class MoodSummary(BaseModel):
    """情绪数据摘要"""
    avg_mood_score: Optional[float] = None
    avg_energy_level: Optional[float] = None
    avg_stress_level: Optional[float] = None
    record_days: int = 0
    top_mood_tags: List[str] = Field(default_factory=list)
    top_triggers: List[str] = Field(default_factory=list)


class CheckinSummary(BaseModel):
    """打卡完成摘要"""
    total_checkins: int = 0
    avg_completion_rate: Optional[float] = None
    active_templates: int = 0
    best_streak: int = 0


class VitalSignsSummary(BaseModel):
    """体征数据摘要"""
    avg_resting_heart_rate: Optional[float] = None
    avg_hrv: Optional[float] = None
    avg_stress_level: Optional[float] = None
    avg_body_battery: Optional[float] = None
    avg_spo2: Optional[float] = None
    blood_pressure_readings: int = 0
    avg_systolic: Optional[float] = None
    avg_diastolic: Optional[float] = None


class HealthReportResponse(BaseModel):
    """健康报告响应"""
    id: int
    user_id: int
    report_type: str
    start_date: date
    end_date: date
    title: str

    exercise_summary: Dict[str, Any] = Field(default_factory=dict)
    diet_summary: Dict[str, Any] = Field(default_factory=dict)
    sleep_summary: Dict[str, Any] = Field(default_factory=dict)
    weight_summary: Dict[str, Any] = Field(default_factory=dict)
    mood_summary: Dict[str, Any] = Field(default_factory=dict)
    checkin_summary: Dict[str, Any] = Field(default_factory=dict)
    vital_signs_summary: Dict[str, Any] = Field(default_factory=dict)

    ai_analysis: Optional[str] = None
    ai_recommendations: List[str] = Field(default_factory=list)
    health_score: Optional[int] = None
    comparison: Dict[str, Any] = Field(default_factory=dict)

    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class HealthReportListResponse(BaseModel):
    """报告列表响应"""
    reports: List[HealthReportResponse]
    total: int


class GenerateReportRequest(BaseModel):
    """生成报告请求"""
    report_type: str = Field(..., description="报告类型: weekly / monthly")
    start_date: Optional[date] = Field(None, description="开始日期（可选，不传则自动计算）")
