from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RokidPushupSessionCreate(BaseModel):
    target_reps: int = Field(default=20, ge=1, le=200)
    source_device: str = Field(default="rokid_glasses", max_length=80)
    meta: Optional[Dict[str, Any]] = None


class RokidPushupSessionCreateResponse(BaseModel):
    id: int
    user_id: int
    status: str
    target_reps: int
    source_device: str
    ingest_token: str
    ingest_url: str
    events_url: str
    open_url: str
    created_at: datetime


class RokidPushupSessionResponse(BaseModel):
    id: int
    user_id: int
    status: str
    target_reps: int
    source_device: str
    started_at: datetime
    ended_at: Optional[datetime]
    last_event_at: Optional[datetime]
    created_at: datetime
    meta: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class RokidPushupEventCreate(BaseModel):
    event_type: str = Field(..., max_length=30)
    reps: Optional[int] = Field(default=None, ge=0, le=10000)
    phase: Optional[str] = Field(default=None, max_length=24)
    elbow_angle_deg: Optional[float] = Field(default=None, ge=0.0, le=220.0)
    shoulder_hip_ankle_angle_deg: Optional[float] = Field(default=None, ge=0.0, le=220.0)
    visibility: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    quality_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    payload: Optional[Dict[str, Any]] = None
    occurred_at: Optional[datetime] = None

    @field_validator("event_type")
    @classmethod
    def _normalize_event_type(cls, value: str) -> str:
        text = (value or "").strip().lower()
        allowed = {"pose", "rep", "session_state"}
        if text not in allowed:
            raise ValueError(f"unsupported rokid pushup event_type: {text}")
        return text

    @field_validator("phase")
    @classmethod
    def _normalize_phase(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip().lower()
        if text not in {"unknown", "up", "down", "transition"}:
            raise ValueError(f"unsupported pushup phase: {text}")
        return text


class RokidPushupEventResponse(BaseModel):
    id: int
    session_id: int
    user_id: int
    event_type: str
    reps: Optional[int]
    phase: Optional[str]
    elbow_angle_deg: Optional[float]
    shoulder_hip_ankle_angle_deg: Optional[float]
    visibility: Optional[float]
    quality_score: Optional[float]
    payload: Optional[Dict[str, Any]]
    occurred_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RokidPushupEventListResponse(BaseModel):
    events: list[RokidPushupEventResponse]


class RokidPushupSessionFinishResponse(BaseModel):
    session: RokidPushupSessionResponse
