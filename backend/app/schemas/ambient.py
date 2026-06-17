from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AudioInputCreate(BaseModel):
    intent: str = Field(..., max_length=40)
    transcript: str = Field(..., min_length=1, max_length=1000)
    source: str = Field(default="ambient_audio", max_length=50)
    device_type: str = Field(default="unknown", max_length=40)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    captured_at: Optional[datetime] = None
    privacy_class: str = Field(default="health_l3", max_length=30)
    meta: Optional[Dict[str, Any]] = None

    @field_validator("intent")
    @classmethod
    def _normalize_intent(cls, value: str) -> str:
        text = (value or "").strip().lower()
        allowed = {"food", "symptom", "fatigue", "mood", "supplement", "medication", "note"}
        if text not in allowed:
            raise ValueError(f"unsupported audio intent: {text}")
        return text

    @field_validator("transcript")
    @classmethod
    def _strip_transcript(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("transcript cannot be blank")
        return text


class AudioInputEventResponse(BaseModel):
    id: int
    intent: str
    transcript: str
    source: str
    device_type: str
    confidence: Optional[float]
    status: str
    target_type: Optional[str]
    target_id: Optional[int]
    write_intent_id: Optional[int]
    captured_at: datetime
    created_at: datetime
    meta: Optional[Dict[str, Any]] = None
    safety_result: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class AmbientAudioInputResponse(BaseModel):
    event: AudioInputEventResponse
    recommended_next_action: Optional[Dict[str, str]] = None


class VisualInputCreate(BaseModel):
    intent: str = Field(..., max_length=40)
    source: str = Field(default="rokid_glasses", max_length=50)
    device_type: str = Field(default="glasses", max_length=40)
    image_uri: Optional[str] = Field(default=None, max_length=1000)
    image_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    ocr_text: Optional[str] = Field(default=None, max_length=4000)
    recognition_result: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    captured_at: Optional[datetime] = None
    privacy_class: str = Field(default="health_l3", max_length=30)
    meta: Optional[Dict[str, Any]] = None

    @field_validator("intent")
    @classmethod
    def _normalize_intent(cls, value: str) -> str:
        text = (value or "").strip().lower()
        allowed = {
            "food_scan",
            "medication_scan",
            "supplement_scan",
            "label_scan",
            "environment_scan",
            "note_scan",
        }
        if text not in allowed:
            raise ValueError(f"unsupported visual intent: {text}")
        return text


class VisualInputEventResponse(BaseModel):
    id: int
    intent: str
    source: str
    device_type: str
    image_uri: Optional[str]
    image_sha256: Optional[str]
    ocr_text: Optional[str]
    recognition_result: Optional[Dict[str, Any]]
    confidence: Optional[float]
    status: str
    privacy_class: str
    target_type: Optional[str]
    target_id: Optional[int]
    write_intent_id: Optional[int]
    captured_at: datetime
    created_at: datetime
    meta: Optional[Dict[str, Any]] = None
    safety_result: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class AmbientVisualInputResponse(BaseModel):
    event: VisualInputEventResponse
    recommended_next_action: Optional[Dict[str, str]] = None


class GlanceCardCreate(BaseModel):
    surface: str = Field(default="rokid_glasses", max_length=40)
    card_type: str = Field(default="action_prompt", max_length=40)
    title: str = Field(..., min_length=1, max_length=40)
    body: str = Field(..., min_length=1, max_length=120)
    priority: str = Field(default="normal", max_length=20)
    action: Optional[Dict[str, Any]] = None
    target_type: Optional[str] = Field(default=None, max_length=50)
    target_id: Optional[int] = None
    expires_at: Optional[datetime] = None
    meta: Optional[Dict[str, Any]] = None

    @field_validator("title", "body")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("text cannot be blank")
        return text


class GlanceCardResponse(BaseModel):
    id: int
    surface: str
    card_type: str
    title: str
    body: str
    priority: str
    status: str
    action: Optional[Dict[str, Any]]
    target_type: Optional[str]
    target_id: Optional[int]
    expires_at: Optional[datetime]
    created_at: datetime
    meta: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class HearingHealthTaskCreate(BaseModel):
    task_type: str = Field(default="hearing_test", max_length=40)
    reason: Optional[str] = Field(default=None, max_length=500)
    source: str = Field(default="ambient_hearing", max_length=50)
    due_at: Optional[datetime] = None
    priority: str = Field(default="normal", max_length=20)
    payload: Optional[Dict[str, Any]] = None

    @field_validator("task_type")
    @classmethod
    def _normalize_task_type(cls, value: str) -> str:
        text = (value or "").strip().lower()
        allowed = {"hearing_test", "noise_review", "audiology_followup"}
        if text not in allowed:
            raise ValueError(f"unsupported hearing task type: {text}")
        return text


class HearingHealthTaskResponse(BaseModel):
    id: int
    task_type: str
    status: str
    source: str
    reason: Optional[str]
    due_at: Optional[datetime]
    priority: str
    write_intent_id: Optional[int]
    payload: Optional[Dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HearingHealthTaskEnvelope(BaseModel):
    task: HearingHealthTaskResponse
    write_intent: Optional[Dict[str, Any]]
