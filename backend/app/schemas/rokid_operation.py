import json
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


FORBIDDEN_DIAGNOSTIC_KEYS = {
    "audio_base64",
    "audio_bytes",
    "base64",
    "base64_audio",
    "base64_photo",
    "image_base64",
    "pcm_base64",
    "photo_base64",
    "raw_audio",
    "raw_photo",
    "raw_video",
    "video_base64",
}

TERMINAL_OPERATION_STATES = {"succeeded", "failed", "cancelled", "completed"}


def _strip_nonempty(value: str, field_name: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{field_name} cannot be blank")
    return text


def _find_forbidden_media_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in FORBIDDEN_DIAGNOSTIC_KEYS:
                return str(key)
            found = _find_forbidden_media_key(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_forbidden_media_key(child)
            if found:
                return found
    return None


def _validate_no_raw_media(value: Dict[str, Any] | None, field_name: str) -> Dict[str, Any] | None:
    if value is None:
        return value
    forbidden = _find_forbidden_media_key(value)
    if forbidden:
        raise ValueError(f"{field_name} cannot include raw media field: {forbidden}")
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    if len(serialized) > 20000:
        raise ValueError(f"{field_name} payload is too large")
    return value


class RokidOperationCreate(BaseModel):
    operation_id: Optional[str] = Field(default=None, max_length=80)
    type: str = Field(..., max_length=60)
    state: str = Field(default="queued", max_length=30)
    primary_surface: str = Field(default="rokid_glasses", max_length=80)
    summary: Optional[str] = Field(default=None, max_length=1000)
    last_error_code: Optional[str] = Field(default=None, max_length=120)
    meta: Optional[Dict[str, Any]] = None
    entity_refs: Optional[Dict[str, Any]] = None
    write_intent_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_client_names(cls, value):
        if isinstance(value, dict):
            data = dict(value)
            if "type" not in data and "capability" in data:
                data["type"] = data["capability"]
            if "state" not in data and "status" in data:
                data["state"] = data["status"]
            if "primary_surface" not in data and "source_device" in data:
                data["primary_surface"] = data["source_device"]
            return data
        return value

    @field_validator("operation_id")
    @classmethod
    def _normalize_operation_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        return text

    @field_validator("type", "state", "primary_surface")
    @classmethod
    def _normalize_required_text(cls, value: str, info):
        return _strip_nonempty(value, info.field_name)

    @field_validator("meta", "entity_refs")
    @classmethod
    def _reject_raw_media(cls, value: Optional[Dict[str, Any]], info):
        return _validate_no_raw_media(value, info.field_name)


class RokidOperationResponse(BaseModel):
    id: int
    operation_id: str
    user_id: int
    type: str = Field(alias="operation_type")
    state: str
    primary_surface: str
    summary: Optional[str]
    last_error_code: Optional[str]
    meta: Optional[Dict[str, Any]]
    entity_refs: Optional[Dict[str, Any]]
    write_intent_id: Optional[int]
    started_at: datetime
    finished_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class RokidOperationEventCreate(BaseModel):
    event_type: str = Field(..., max_length=60)
    phase: Optional[str] = Field(default=None, max_length=60)
    severity: str = Field(default="info", max_length=20)
    state: Optional[str] = Field(default=None, max_length=30)
    message: Optional[str] = Field(default=None, max_length=1000)
    payload: Optional[Dict[str, Any]] = None
    occurred_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_status(cls, value):
        if isinstance(value, dict) and "state" not in value and "status" in value:
            data = dict(value)
            data["state"] = data["status"]
            return data
        return value

    @field_validator("event_type", "severity")
    @classmethod
    def _normalize_required_text(cls, value: str, info):
        return _strip_nonempty(value, info.field_name).lower()

    @field_validator("phase", "state")
    @classmethod
    def _normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("payload")
    @classmethod
    def _reject_raw_media(cls, value: Optional[Dict[str, Any]]):
        return _validate_no_raw_media(value, "payload")


class RokidOperationTraceEventResponse(BaseModel):
    id: int
    operation_id: str
    user_id: int
    event_type: str
    phase: Optional[str]
    severity: str
    message: Optional[str]
    payload: Optional[Dict[str, Any]]
    occurred_at: datetime
    created_at: datetime


class RokidOperationTimelineResponse(BaseModel):
    operation: RokidOperationResponse
    events: list[RokidOperationTraceEventResponse]


class RokidDiagnosticUpload(BaseModel):
    operation_id: str = Field(..., min_length=1, max_length=80)
    summary: str = Field(..., min_length=1, max_length=1000)
    diagnostics: Dict[str, Any]
    severity: str = Field(default="warn", max_length=20)
    occurred_at: Optional[datetime] = None

    @field_validator("operation_id", "summary", "severity")
    @classmethod
    def _strip_text(cls, value: str, info):
        return _strip_nonempty(value, info.field_name)

    @model_validator(mode="after")
    def _reject_raw_media(self):
        _validate_no_raw_media(self.diagnostics, "diagnostics")
        return self
