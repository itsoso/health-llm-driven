"""聊天相关 Schema"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ChatSendRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    is_kids_mode: Optional[bool] = False
    image_base64: Optional[str] = None
    image_type: Optional[str] = "jpeg"
    mode: Optional[str] = None  # None=健康助理, "proxy"=OpenClaw代理


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DietSavedData(BaseModel):
    record_id: int
    food_items: str
    total_calories: Optional[float] = None
    total_protein: Optional[float] = None
    total_carbs: Optional[float] = None
    total_fat: Optional[float] = None
    meal_type: str
    record_date: str


class ActivitySavedData(BaseModel):
    type: str  # checkin, water, supplement, symptom
    status: str  # saved, updated, already_exists
    message: str  # 人类可读摘要


class ReminderData(BaseModel):
    reminder_minutes: int       # 多少分钟后提醒
    reminder_message: str       # 提醒内容
    activity_name: str          # 活动名称


class ChatSendResponse(BaseModel):
    conversation_id: int
    reply: str
    message_id: int
    diet_saved: Optional[bool] = None
    diet_data: Optional[DietSavedData] = None
    activities_saved: Optional[bool] = None
    activities: Optional[List[ActivitySavedData]] = None
    reminder: Optional[ReminderData] = None


class TranscribeRequest(BaseModel):
    audio_base64: str
    audio_format: str = "mp3"


class TranscribeResponse(BaseModel):
    text: str


class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    last_message: Optional[str] = None
    mode: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(BaseModel):
    id: int
    title: str
    messages: List[ChatMessageResponse]
    mode: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
