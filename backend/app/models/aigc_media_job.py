"""Owner-scoped ledger for Xiaoba AIGC image and video work."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class AIGCMediaJob(Base):
    __tablename__ = "aigc_media_jobs"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("agent_conversations.id", ondelete="SET NULL"), nullable=True)
    source_message_id = Column(Integer, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    source_image_index = Column(Integer, nullable=True)

    kind = Column(String(32), nullable=False)
    status = Column(String(20), nullable=False, default="queued", index=True)
    progress = Column(Integer, nullable=False, default=0)
    model = Column(String(80), nullable=False)
    provider_task_id = Column(String(128), nullable=True, unique=True)
    idempotency_key = Column(String(128), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)

    output_filename = Column(String(256), nullable=True)
    output_media_type = Column(String(32), nullable=True)
    result_metadata = Column(JSONColumn, nullable=True)
    provider_error_code = Column(String(120), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    last_provider_checked_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_aigc_media_jobs_user_idempotency"),
        # A second confirmation for an identical immutable request must open
        # the original ledger row rather than submit a second billed task.
        UniqueConstraint("user_id", "request_fingerprint", name="uq_aigc_media_jobs_user_fingerprint"),
        Index("idx_aigc_media_jobs_user_created", "user_id", "created_at"),
        Index("idx_aigc_media_jobs_user_status", "user_id", "status"),
    )
