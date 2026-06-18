"""Rokid glasses push-up coaching session models."""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class RokidPushupSession(Base):
    """A short-lived session that lets a glasses-side app ingest pose events."""

    __tablename__ = "rokid_pushup_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    status = Column(String(24), nullable=False, default="active", index=True)
    target_reps = Column(Integer, nullable=False, default=20)
    source_device = Column(String(80), nullable=False, default="rokid_glasses")
    ingest_token_hash = Column(String(64), nullable=False, index=True)
    meta = Column(JSONColumn, nullable=True)

    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    ended_at = Column(DateTime(timezone=True), nullable=True)
    last_event_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_rokid_pushup_sessions_user_status", "user_id", "status"),
    )


class RokidPushupEvent(Base):
    """A pose, rep, or session-state event emitted by the glasses-side app."""

    __tablename__ = "rokid_pushup_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("rokid_pushup_sessions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    event_type = Column(String(30), nullable=False, index=True)
    reps = Column(Integer, nullable=True)
    phase = Column(String(24), nullable=True)
    elbow_angle_deg = Column(Float, nullable=True)
    shoulder_hip_ankle_angle_deg = Column(Float, nullable=True)
    visibility = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    payload = Column(JSONColumn, nullable=True)

    occurred_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_rokid_pushup_events_session_id", "session_id", "id"),
        Index("idx_rokid_pushup_events_user_occurred", "user_id", "occurred_at"),
    )
