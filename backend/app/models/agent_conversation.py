"""Agent conversation persistence models.

The physical table names are kept for compatibility with existing production
data. New code should use AgentConversation / AgentMessage names.
"""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class AgentConversation(Base):
    """Unified health assistant conversation."""

    __tablename__ = "openclaw_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), default="新对话")
    session_key = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    messages = relationship(
        "AgentMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AgentMessage.created_at",
    )

    __table_args__ = (
        Index("ix_openclaw_conv_user_updated", "user_id", "updated_at"),
    )


class AgentMessage(Base):
    """Unified health assistant message."""

    __tablename__ = "openclaw_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("openclaw_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    conversation = relationship("AgentConversation", back_populates="messages")
