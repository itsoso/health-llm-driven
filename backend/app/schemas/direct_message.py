"""私信消息 schemas"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class DMSendRequest(BaseModel):
    receiver_id: int
    content: str = Field(..., min_length=1, max_length=500)


class DMResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    is_read: bool
    created_at: datetime
    sender_name: Optional[str] = None
    sender_avatar: Optional[str] = None

    class Config:
        from_attributes = True


class DMConversationItem(BaseModel):
    friend_id: int
    friend_name: str
    friend_avatar: Optional[str] = None
    last_message: str
    last_message_time: datetime
    unread_count: int


class DMHistoryResponse(BaseModel):
    messages: List[DMResponse]
    has_more: bool


class DMUnreadCountResponse(BaseModel):
    total_unread: int
