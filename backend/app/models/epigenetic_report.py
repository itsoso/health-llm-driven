"""Experimental epigenetic report summaries."""

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class EpigeneticReport(Base):
    """Commercial epigenetic clock report with an explicit experimental boundary."""

    __tablename__ = "epigenetic_reports"
    __table_args__ = (
        Index("idx_epigenetic_reports_user_sample_date", "user_id", "sample_date"),
        Index("idx_epigenetic_reports_user_clock", "user_id", "clock_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    vendor = Column(String(120), nullable=False)
    sample_date = Column(Date, nullable=False)
    clock_type = Column(String(120), nullable=False)
    biological_age = Column(Float)
    pace_of_aging = Column(Float)
    confidence = Column(String(20), nullable=False, default="low")
    raw_summary = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
