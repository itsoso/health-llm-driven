"""Explicitly opted-in GPS sessions; payloads never have plaintext fallback."""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    Text,
    text,
)
from app.database import Base
from app.models._encrypted import StrictEncryptedString


class StrictJourneyText(StrictEncryptedString):
    impl = Text
    cache_ok = True


class DailyJourneyRequest(Base):
    """Opaque replay barrier survives payload deletion, removed with owner account."""

    __tablename__ = "daily_journey_requests"
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    request_id = Column(String(36), primary_key=True)
    session_id = Column(String(36), nullable=False, unique=True)


class DailyJourneySession(Base):
    __tablename__ = "daily_journey_sessions"
    id = Column(String(36), primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_id = Column(String(36), nullable=False)
    local_date = Column(Date, nullable=False)
    timezone = Column(String(64), nullable=False)
    status = Column(String(8), nullable=False, default="active")
    version = Column(Integer, nullable=False, default=1)
    segment = Column(Integer, nullable=False, default=1)
    last_state_command = Column(String(64))
    started_at = Column(DateTime(timezone=True), nullable=False)
    segment_started_at = Column(DateTime(timezone=True), nullable=False)
    segment_ended_at = Column(DateTime(timezone=True))
    deadline_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    retention_days = Column(Integer, nullable=False)
    point_count = Column(Integer, nullable=False, default=0)
    annotations = Column(StrictJourneyText, nullable=False, default="{}")
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'ended')", name="ck_daily_journey_status"
        ),
        CheckConstraint("retention_days IN (1, 7)", name="ck_daily_journey_retention"),
        CheckConstraint("version > 0 AND segment > 0", name="ck_daily_journey_version"),
        CheckConstraint(
            "point_count >= 0 AND point_count <= 10000", name="ck_daily_journey_count"
        ),
        Index("ix_daily_journey_owner_day", "user_id", "local_date"),
        Index("ix_daily_journey_expiry", "expires_at"),
        Index(
            "uq_daily_journey_unfinished_owner",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'paused')"),
            sqlite_where=text("status IN ('active', 'paused')"),
        ),
    )


class DailyJourneyPoint(Base):
    __tablename__ = "daily_journey_points"
    session_id = Column(
        String(36),
        ForeignKey("daily_journey_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id = Column(String(36), primary_key=True)
    segment = Column(Integer, nullable=False)
    payload = Column(StrictJourneyText, nullable=False)
    __table_args__ = (
        CheckConstraint("segment > 0", name="ck_daily_journey_point_segment"),
    )
