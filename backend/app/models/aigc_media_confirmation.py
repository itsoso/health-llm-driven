"""One-time, owner-scoped consent records for external AIGC dispatch."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class AIGCMediaConfirmation(Base):
    """Server-authored AIGC draft that can be consumed only by its owner.

    The prompt is encrypted at rest because the record exists solely to bridge
    an Agent draft and the user's explicit button click.  It must never be
    supplied back by a client at confirmation time.
    """

    __tablename__ = "aigc_media_confirmations"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("agent_conversations.id", ondelete="SET NULL"), nullable=True)
    source_message_id = Column(Integer, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    source_image_index = Column(Integer, nullable=True)

    kind = Column(String(32), nullable=False)
    purpose = Column(String(48), nullable=False)
    model = Column(String(80), nullable=False)
    prompt_ciphertext = Column(Text, nullable=False)
    prompt_fingerprint = Column(String(64), nullable=False)
    duration_seconds = Column(Integer, nullable=False, default=5)
    ratio = Column(String(12), nullable=False, default="9:16")

    # pending -> dispatching -> dispatched.  A conditional update consumes the
    # record so duplicated taps and concurrent requests cannot duplicate spend.
    status = Column(String(20), nullable=False, default="pending", index=True)
    job_id = Column(String(64), ForeignKey("aigc_media_jobs.id", ondelete="SET NULL"), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_aigc_media_confirmations_owner_state", "user_id", "status", "expires_at"),
    )
