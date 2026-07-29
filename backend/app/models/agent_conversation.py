"""Agent conversation persistence models."""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class AgentConversation(Base):
    """Unified health assistant conversation."""

    __tablename__ = "agent_conversations"

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
        Index("ix_agent_conv_user_updated", "user_id", "updated_at"),
        Index(
            "uq_agent_conv_user_session_key",
            "user_id",
            "session_key",
            unique=True,
            postgresql_where=text("session_key LIKE 'external-%'"),
            sqlite_where=text("session_key LIKE 'external-%'"),
        ),
    )


class AgentMessage(Base):
    """Unified health assistant message."""

    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)
    meta = Column(JSONB, nullable=True)
    client_turn_id = Column(String(112), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    conversation = relationship("AgentConversation", back_populates="messages")

    __table_args__ = (
        Index("ix_agent_messages_client_turn_id", "client_turn_id"),
        Index(
            "uq_agent_messages_user_client_turn",
            "client_turn_id",
            unique=True,
            postgresql_where=text("role = 'user' AND client_turn_id IS NOT NULL"),
            sqlite_where=text("role = 'user' AND client_turn_id IS NOT NULL"),
        ),
    )
