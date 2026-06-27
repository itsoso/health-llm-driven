"""Health Runtime governance controls.

These objects cover per-user data-source quality, source preference overrides,
and user controls for derived predictions/memory categories.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text

from app.database import Base
from app.models.agent_audit_log import JSONColumn


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataSourceQuality(Base):
    __tablename__ = "data_source_quality"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_kind = Column(String(40), nullable=False, index=True)
    source_id = Column(String(160), nullable=False)
    metric = Column(String(80), nullable=False, index=True)
    quality_score = Column(Float, nullable=False, default=0.0)
    confidence = Column(String(30), nullable=False, default="unknown")
    freshness_seconds = Column(Integer, nullable=True)
    status = Column(String(30), nullable=False, default="usable", index=True)
    reason = Column(Text, nullable=True)
    source_metadata = Column("metadata", JSONColumn, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_data_source_quality_user_source_metric", "user_id", "source_kind", "source_id", "metric", unique=True),
    )


class UserDataSourcePreference(Base):
    __tablename__ = "user_data_source_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    metric = Column(String(80), nullable=False, index=True)
    preferred_source_kind = Column(String(40), nullable=False)
    preferred_source_id = Column(String(160), nullable=False)
    scope = Column(String(80), nullable=False, default="global", index=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_user_source_preferences_user_metric_scope", "user_id", "metric", "scope", unique=True),
    )


class HealthRuntimeControl(Base):
    __tablename__ = "health_runtime_controls"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    control_type = Column(String(40), nullable=False, index=True)
    target_key = Column(String(120), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="active", index=True)
    reason = Column(Text, nullable=True)
    control_metadata = Column("metadata", JSONColumn, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_health_runtime_controls_user_target", "user_id", "control_type", "target_key", unique=True),
    )
