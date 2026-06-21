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


class VisualInputEvent(Base):
    """A first-person visual capture or OCR result from Rokid-style glasses."""

    __tablename__ = "visual_input_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    captured_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    device_type = Column(String(40), nullable=False, default="glasses")
    source = Column(String(50), nullable=False, default="rokid_glasses")
    intent = Column(String(40), nullable=False, index=True)

    image_uri = Column(Text, nullable=True)
    image_sha256 = Column(String(64), nullable=True)
    ocr_text = Column(Text, nullable=True)
    recognition_result = Column(JSONColumn, nullable=True)
    confidence = Column(Float, nullable=True)

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
        Index("idx_visual_input_user_captured", "user_id", "captured_at"),
        Index("idx_visual_input_user_intent", "user_id", "intent"),
    )


class MealMonitoringSession(Base):
    """A 准视频 (periodic-sampling) meal monitoring session.

    During a meal the client samples one frame every ~5s; each frame is stored
    as a ``VisualInputEvent`` linked back here via ``meta.meal_session_id``. At
    finish the session's frames are batch-analyzed into a DRAFT food/nutrition
    summary (R4: draft+confirm, never confidence-autowrite) plus an OBSERVATIONAL
    post-meal nutrition summary.

    Raw frame images are deleted at ``raw_media_delete_at`` (+7d); only the
    analysis notes / summary persist after that.
    """

    __tablename__ = "meal_monitoring_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # active -> analyzing -> needs_confirmation -> confirmed | aborted
    status = Column(String(30), nullable=False, default="active", index=True)
    source = Column(String(50), nullable=False, default="rokid_glasses")
    device_type = Column(String(40), nullable=False, default="glasses")

    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    ended_at = Column(DateTime(timezone=True), nullable=True)
    consent_at = Column(DateTime(timezone=True), nullable=True)

    frame_count = Column(Integer, nullable=False, default=0)
    privacy_class = Column(String(30), nullable=False, default="health_l3")
    # Raw frame images must be purged at this time (privacy: +7d default).
    raw_media_delete_at = Column(DateTime(timezone=True), nullable=True, index=True)
    raw_media_deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Observational draft + post-meal summary (no raw images, safe to persist).
    summary = Column(JSONColumn, nullable=True)

    write_intent_id = Column(Integer, ForeignKey("write_intents.id"), nullable=True, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)
    meta = Column(JSONColumn, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_meal_sessions_user_status", "user_id", "status"),
        Index("idx_meal_sessions_user_started", "user_id", "started_at"),
    )


class GlanceCard(Base):
    """A short-lived, glanceable action prompt for glasses or other surfaces."""

    __tablename__ = "glance_cards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    surface = Column(String(40), nullable=False, default="rokid_glasses", index=True)
    card_type = Column(String(40), nullable=False, default="action_prompt", index=True)
    title = Column(String(80), nullable=False)
    body = Column(Text, nullable=False)
    priority = Column(String(20), nullable=False, default="normal")
    status = Column(String(20), nullable=False, default="active", index=True)
    action = Column(JSONColumn, nullable=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    displayed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSONColumn, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_glance_cards_user_surface_status", "user_id", "surface", "status"),
        Index("idx_glance_cards_user_expires", "user_id", "expires_at"),
    )
