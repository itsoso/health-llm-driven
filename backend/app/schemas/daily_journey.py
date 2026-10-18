"""Bounded authenticated GPS wire contracts. Raw location is never model context."""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID
import unicodedata
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from app.schemas.journey import validated_timezone

Mode = Literal["unknown", "walking", "cycling", "vehicle"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class JourneyStart(StrictModel):
    request_id: UUID
    client_id: UUID
    timezone: str
    retention_days: Literal[1, 7] = 7
    consent: Literal[True]

    @field_validator("consent", mode="before")
    @classmethod
    def consent_explicit(cls, value):
        if value is not True:
            raise ValueError("请明确同意行程采集")
        return value

    @field_validator("retention_days", mode="before")
    @classmethod
    def retention_int(cls, value):
        if type(value) is not int:
            raise ValueError("保留期限无效")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, value):
        return validated_timezone(value)


class JourneyStateChange(StrictModel):
    action: Literal["pause", "resume", "end"]
    expected_version: StrictInt = Field(ge=1)
    client_id: UUID


class JourneyPoint(StrictModel):
    id: UUID
    recorded_at: datetime
    latitude: float = Field(ge=-90, le=90, strict=True)
    longitude: float = Field(ge=-180, le=180, strict=True)
    accuracy_m: float = Field(ge=0, le=10000, strict=True)
    speed_mps: float | None = Field(default=None, ge=0, le=200, strict=True)

    @field_validator("recorded_at", mode="before")
    @classmethod
    def timestamp_string(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("时间格式无效")
        return value

    @field_validator("recorded_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value.astimezone(timezone.utc)


class JourneyBatch(StrictModel):
    client_id: UUID
    segment: StrictInt = Field(ge=1)
    points: list[JourneyPoint] = Field(min_length=1, max_length=100)


class JourneyAnnotation(StrictModel):
    target_id: str = Field(min_length=1, max_length=80)
    label: str | None = Field(default=None, max_length=80)
    mode: Mode | None = None

    @field_validator("label")
    @classmethod
    def safe_label(cls, value):
        if value is None:
            return None
        if any(unicodedata.category(c).startswith("C") or c in "<>" for c in value):
            raise ValueError("名称包含无效字符")
        return value.strip() or None


class JourneyAnnotations(StrictModel):
    expected_version: StrictInt = Field(ge=1)
    annotations: list[JourneyAnnotation] = Field(max_length=100)


class JourneySessionResponse(StrictModel):
    id: str
    client_id: str
    local_date: date
    timezone: str
    status: Literal["active", "paused", "ended"]
    version: int
    segment: int
    started_at: datetime
    deadline_at: datetime
    ended_at: datetime | None
    expires_at: datetime
    retention_days: int
    point_count: int


class JourneySessionList(StrictModel):
    items: list[JourneySessionResponse]


class JourneyUploadResponse(StrictModel):
    accepted: int
    duplicate: int
    session: JourneySessionResponse


class JourneyReviewPoint(JourneyPoint):
    segment: int


class JourneySegment(StrictModel):
    id: str
    point_ids: list[str]
    started_at: datetime
    ended_at: datetime
    distance_m: float
    distance_display: str
    mode: Mode
    mode_source: Literal["estimated", "user"]
    label: str | None


class JourneyStop(StrictModel):
    id: str
    latitude: float
    longitude: float
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    duration_display: str
    label: str | None


class JourneyGap(StrictModel):
    started_at: datetime
    ended_at: datetime
    reason: Literal["pause", "signal_gap", "low_accuracy", "implausible_speed"]


class JourneySummary(StrictModel):
    distance_m: float
    distance_display: str
    observed_seconds: float
    observed_display: str
    stop_count: int
    point_count: int
    note: str


class JourneyReview(StrictModel):
    session: JourneySessionResponse
    points: list[JourneyReviewPoint]
    segments: list[JourneySegment]
    stops: list[JourneyStop]
    gaps: list[JourneyGap]
    summary: JourneySummary
