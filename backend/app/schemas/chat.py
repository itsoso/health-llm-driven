"""聊天相关 Schema"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ChatSendRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class DietSavedData(BaseModel):
    record_id: int
    food_items: str
    total_calories: Optional[float] = None
    total_protein: Optional[float] = None
    total_carbs: Optional[float] = None
    total_fat: Optional[float] = None
    meal_type: str
    record_date: str


class ChatSendResponse(BaseModel):
    conversation_id: int
    reply: str
    message_id: int
    diet_saved: Optional[bool] = None
    diet_data: Optional[DietSavedData] = None


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

    class Config:
        from_attributes = True


class ConversationDetailResponse(BaseModel):
    id: int
    title: str
    messages: List[ChatMessageResponse]

    class Config:
        from_attributes = True
