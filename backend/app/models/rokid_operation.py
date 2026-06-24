"""Generic Rokid operation ledger models.

This table is a thin trace anchor for cross-device debugging. Domain records
such as ``meal_monitoring_sessions``, visual input drafts, and
``rokid_pushup_sessions`` stay in their own tables. Per-step traces are written
to existing ``client_events`` and referenced from ``entity_refs`` so Rokid does
not grow a parallel event system.
"""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class RokidOperation(Base):
    """A user-visible Rokid action spanning phone, companion app, glasses, and server."""

    __tablename__ = "rokid_operations"

    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(String(80), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    operation_type = Column("type", String(60), nullable=False, index=True)
    state = Column(String(30), nullable=False, default="queued", index=True)
    primary_surface = Column(String(80), nullable=False, default="rokid_glasses")
    summary = Column(Text, nullable=True)
    last_error_code = Column(String(120), nullable=True)
    meta = Column(JSONColumn, nullable=True)
    entity_refs = Column(JSONColumn, nullable=True)
    write_intent_id = Column(Integer, ForeignKey("write_intents.id"), nullable=True, index=True)

    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_rokid_operations_user_started", "user_id", "started_at"),
        Index("idx_rokid_operations_user_state", "user_id", "state"),
    )
