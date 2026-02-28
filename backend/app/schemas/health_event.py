"""健康事件流 Schema"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


class EventStatusEnum(str, Enum):
    pending = "pending"
    auto_confirmed = "auto_confirmed"
    confirmed = "confirmed"
    corrected = "corrected"
    dismissed = "dismissed"


# ========== HealthEvent Schemas ==========

class HealthEventIngest(BaseModel):
    """事件摄入请求 - 来自设备/传感器/NFC"""
    event_type: str = Field(..., description="事件类型: weight, blood_pressure, water, excretion, supplement, exercise, diet")
    source: str = Field(..., description="来源: nfc_tag, bluetooth_scale, voice, photo, manual, api")
    source_device_id: Optional[str] = None
    raw_data: Optional[dict] = None
    event_time: Optional[datetime] = None


class HealthEventConfirm(BaseModel):
    """用户确认/修正事件"""
    confirmed_data: Optional[dict] = None  # None 表示接受 AI 推理结果
    status: EventStatusEnum = EventStatusEnum.confirmed


class HealthEventResponse(BaseModel):
    """事件响应"""
    id: int
    user_id: int
    event_type: str
    source: str
    source_device_id: Optional[str] = None
    raw_data: Optional[dict] = None
    ai_inference: Optional[dict] = None
    confidence: float = 0.0
    status: EventStatusEnum
    confirmed_data: Optional[dict] = None
    target_record_type: Optional[str] = None
    target_record_id: Optional[int] = None
    event_time: datetime
    created_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BatchConfirmRequest(BaseModel):
    """批量确认请求"""
    event_ids: List[int]


class PendingEventsSummary(BaseModel):
    """待确认事件摘要"""
    total: int
    by_type: dict  # {"weight": 2, "water": 1, ...}
    events: List[HealthEventResponse]


# ========== EventSource Schemas ==========

class EventSourceCreate(BaseModel):
    """创建事件来源"""
    source_type: str = Field(..., description="来源类型: nfc_tag, bluetooth_scale, bluetooth_bp, api_webhook")
    device_id: str = Field(..., description="设备标识")
    name: str = Field(..., description="显示名称")
    event_type: str = Field(..., description="绑定的事件类型")
    config: Optional[dict] = None
    auto_confirm_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class EventSourceUpdate(BaseModel):
    """更新事件来源"""
    name: Optional[str] = None
    event_type: Optional[str] = None
    config: Optional[dict] = None
    auto_confirm_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    is_active: Optional[str] = None


class EventSourceResponse(BaseModel):
    """事件来源响应"""
    id: int
    user_id: int
    source_type: str
    device_id: str
    name: str
    event_type: str
    config: Optional[dict] = None
    auto_confirm_threshold: float
    is_active: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
