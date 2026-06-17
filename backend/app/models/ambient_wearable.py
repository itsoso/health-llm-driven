"""Ambient wearable input models.

These tables keep glasses/earbuds/shoes style inputs as source events. Product
logic still flows through Health Router, SafetyGuardian, HealthAgenda, and
WriteIntent instead of trusting device-side conclusions.
"""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class AudioInputEvent(Base):
    """A short audio transcript from Watch, earbuds, Siri, or mobile voice."""

    __tablename__ = "audio_input_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    captured_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    device_type = Column(String(40), nullable=False, default="unknown")
    source = Column(String(50), nullable=False, default="ambient_audio")
    intent = Column(String(40), nullable=False, index=True)
    transcript = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)

    # pending_confirmation: a draft needs user confirmation.
    # processed: the endpoint already wrote/evaluated the target record.
    # failed: capture was persisted but routing/evaluation failed.
    status = Column(String(30), nullable=False, default="pending_confirmation", index=True)
    privacy_class = Column(String(30), nullable=False, default="health_l3")

    write_intent_id = Column(Integer, ForeignKey("write_intents.id"), nullable=True, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)

    safety_result = Column(JSONColumn, nullable=True)
    meta = Column(JSONColumn, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_audio_input_user_captured", "user_id", "captured_at"),
        Index("idx_audio_input_user_intent", "user_id", "intent"),
    )


class HearingHealthTask(Base):
    """A hearing/noise health task that can become a manual-confirm reminder."""

    __tablename__ = "hearing_health_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    task_type = Column(String(40), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    source = Column(String(50), nullable=False, default="ambient_hearing")
    reason = Column(Text, nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    priority = Column(String(20), nullable=False, default="normal")
    write_intent_id = Column(Integer, ForeignKey("write_intents.id"), nullable=True, index=True)
    payload = Column(JSONColumn, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_hearing_tasks_user_status", "user_id", "status"),
        Index("idx_hearing_tasks_user_type_status", "user_id", "task_type", "status"),
    )
