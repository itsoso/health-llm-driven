"""Persistent NFC bowel timer state."""

from sqlalchemy import Column, DateTime, Integer

from app.database import Base


class BowelTimer(Base):
    """Persist an active bowel timer across process restarts."""

    __tablename__ = "bowel_timers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
