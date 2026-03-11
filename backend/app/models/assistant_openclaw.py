"""智能助理专用 OpenClaw 绑定与会话模型"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class AssistantOpenClawBinding(Base):
    """用户绑定的智能助理专用 OpenClaw 实例"""

    __tablename__ = "assistant_openclaw_bindings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    display_name = Column(String(100), nullable=False, default="我的 OpenClaw")
    gateway_url = Column(String(255), nullable=False)
    gateway_token_encrypted = Column(Text, nullable=False)
    gateway_token_last4 = Column(String(8), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="unconfigured")
    last_tested_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AssistantOpenClawConversation(Base):
    """智能助理专用 OpenClaw 对话会话"""

    __tablename__ = "assistant_openclaw_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), default="新对话")
    session_key = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship(
        "AssistantOpenClawMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AssistantOpenClawMessage.created_at",
    )

    __table_args__ = (
        Index("ix_assistant_openclaw_conv_user_updated", "user_id", "updated_at"),
    )


class AssistantOpenClawMessage(Base):
    """智能助理专用 OpenClaw 对话消息"""

    __tablename__ = "assistant_openclaw_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("assistant_openclaw_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("AssistantOpenClawConversation", back_populates="messages")
