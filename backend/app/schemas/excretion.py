"""排泄记录 Schemas"""
from datetime import date, datetime, time
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class ExcretionRecordCreate(BaseModel):
    record_date: date
    record_time: Optional[time] = None
    type: str = Field(..., pattern="^(bowel|urine)$")

    # 大便字段
    stool_type: Optional[int] = Field(None, ge=1, le=7)
    color: Optional[str] = None
    amount: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    blood_present: Optional[bool] = None

    # 小便字段
    urine_color: Optional[str] = None
    urine_amount: Optional[str] = None

    # 共用字段
    urgency: Optional[int] = Field(None, ge=1, le=5)
    pain_level: Optional[int] = Field(None, ge=0, le=5)
    notes: Optional[str] = Field(None, max_length=500)


class ExcretionRecordUpdate(BaseModel):
    stool_type: Optional[int] = Field(None, ge=1, le=7)
    color: Optional[str] = None
    amount: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    blood_present: Optional[bool] = None
    urine_color: Optional[str] = None
    urine_amount: Optional[str] = None
    urgency: Optional[int] = Field(None, ge=1, le=5)
    pain_level: Optional[int] = Field(None, ge=0, le=5)
    notes: Optional[str] = Field(None, max_length=500)


class ExcretionRecordResponse(BaseModel):
    id: int
    user_id: int
    record_date: date
    record_time: Optional[time] = None
    type: str
    stool_type: Optional[int] = None
    color: Optional[str] = None
    amount: Optional[str] = None
    duration_minutes: Optional[int] = None
    blood_present: Optional[bool] = None
    urine_color: Optional[str] = None
    urine_amount: Optional[str] = None
    urgency: Optional[int] = None
    pain_level: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExcretionDailySummary(BaseModel):
    date: date
    bowel_count: int = 0
    urine_count: int = 0
    avg_stool_type: Optional[float] = None
    has_blood: bool = False
    has_pain: bool = False


class ExcretionStats(BaseModel):
    total_records: int = 0
    bowel_count: int = 0
    urine_count: int = 0
    avg_bowel_per_day: Optional[float] = None
    avg_urine_per_day: Optional[float] = None
    avg_stool_type: Optional[float] = None
    stool_type_distribution: Dict[int, int] = Field(default_factory=dict)
    color_distribution: Dict[str, int] = Field(default_factory=dict)
    blood_count: int = 0
    daily_summary: List[ExcretionDailySummary] = Field(default_factory=list)
