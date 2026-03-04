"""睡眠记录 Schemas"""
from datetime import date, datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SleepRecordCreate(BaseModel):
    record_date: date
    bedtime: datetime
    wake_time: datetime
    sleep_quality: int = Field(..., ge=1, le=5)
    wake_count: Optional[int] = Field(0, ge=0)
    had_dream: Optional[bool] = False
    dream_description: Optional[str] = Field(None, max_length=500)
    fall_asleep_difficulty: Optional[int] = Field(None, ge=1, le=5)
    morning_feeling: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = Field(None, max_length=1000)

    @model_validator(mode='after')
    def validate_times(self):
        if self.wake_time <= self.bedtime:
            raise ValueError("醒来时间必须晚于入睡时间")
        return self


class SleepRecordUpdate(BaseModel):
    bedtime: Optional[datetime] = None
    wake_time: Optional[datetime] = None
    sleep_quality: Optional[int] = Field(None, ge=1, le=5)
    wake_count: Optional[int] = Field(None, ge=0)
    had_dream: Optional[bool] = None
    dream_description: Optional[str] = Field(None, max_length=500)
    fall_asleep_difficulty: Optional[int] = Field(None, ge=1, le=5)
    morning_feeling: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = Field(None, max_length=1000)


class SleepRecordResponse(BaseModel):
    id: int
    user_id: int
    record_date: date
    bedtime: datetime
    wake_time: datetime
    sleep_quality: int
    total_duration_minutes: Optional[int] = None
    wake_count: Optional[int] = 0
    had_dream: Optional[bool] = False
    dream_description: Optional[str] = None
    fall_asleep_difficulty: Optional[int] = None
    morning_feeling: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SleepDailyTrend(BaseModel):
    date: date
    sleep_quality: float
    duration_hours: Optional[float] = None
    wake_count: Optional[int] = None
    morning_feeling: Optional[float] = None


class SleepStats(BaseModel):
    total_records: int = 0
    avg_sleep_quality: Optional[float] = None
    avg_duration_hours: Optional[float] = None
    avg_wake_count: Optional[float] = None
    avg_fall_asleep_difficulty: Optional[float] = None
    avg_morning_feeling: Optional[float] = None
    dream_frequency: Optional[float] = None
    quality_distribution: Dict[int, int] = Field(default_factory=dict)
    daily_trend: List[SleepDailyTrend] = Field(default_factory=list)
    avg_bedtime: Optional[str] = None
    avg_wake_time: Optional[str] = None
