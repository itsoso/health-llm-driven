"""按摩/理疗追踪 schemas"""
from pydantic import BaseModel, ConfigDict, Field
from datetime import date, datetime
from typing import Optional, List


class MassageRecordBase(BaseModel):
    record_date: date
    start_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    massage_type: str = "推拿"
    therapist: Optional[str] = None
    body_parts: Optional[str] = None
    price: Optional[float] = None
    issues_before: Optional[str] = None
    treatment_notes: Optional[str] = None
    feeling_after: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None


class MassageRecordCreate(MassageRecordBase):
    pass


class MassageRecordUpdate(BaseModel):
    record_date: Optional[date] = None
    start_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    massage_type: Optional[str] = None
    therapist: Optional[str] = None
    body_parts: Optional[str] = None
    price: Optional[float] = None
    issues_before: Optional[str] = None
    treatment_notes: Optional[str] = None
    feeling_after: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None


class MassageRecordResponse(MassageRecordBase):
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class MassageStats(BaseModel):
    total_sessions: int = 0
    total_duration_minutes: int = 0
    total_cost: float = 0
    avg_rating: Optional[float] = None
    favorite_location: Optional[str] = None
    favorite_therapist: Optional[str] = None
    last_session_date: Optional[date] = None
