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


class ChatSendResponse(BaseModel):
    conversation_id: int
    reply: str
    message_id: int


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
