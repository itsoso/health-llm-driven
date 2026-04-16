"""OpenClaw Channel 对话模型"""
from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base


class OpenClawConversation(Base):
    """OpenClaw 对话会话"""
    __tablename__ = "openclaw_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), default="新对话")
    session_key = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    messages = relationship(
        "OpenClawMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="OpenClawMessage.created_at",
    )

    __table_args__ = (
        Index("ix_openclaw_conv_user_updated", "user_id", "updated_at"),
    )


class OpenClawMessage(Base):
    """OpenClaw 对话消息"""
    __tablename__ = "openclaw_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("openclaw_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)  # 1=thumbs up, -1=thumbs down, NULL=unrated
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    conversation = relationship("OpenClawConversation", back_populates="messages")
