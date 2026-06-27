"""Daily Artifact exposure and action telemetry."""
from datetime import UTC, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class DailyArtifactEvent(Base):
    """Append-only event for the daily top-action artifact."""

    __tablename__ = "daily_artifact_events"
    __table_args__ = (
        Index("idx_daily_artifact_events_user_date", "user_id", "artifact_date"),
        Index("idx_daily_artifact_events_user_event_created", "user_id", "event_type", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    artifact_date = Column(Date, nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    top_action_id = Column(String(200), nullable=True, index=True)
    skip_reason = Column(String(80), nullable=True)
    delivered_context = Column(JSONColumn, nullable=True)
    week_index = Column(Integer, nullable=False, default=1)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
