"""Nocturnal SpO2 Events model (P1b)。

分析夜间 SpO2 时序后落盘的氧降事件。事件表而非原始时序表 —
原始 spo2_samples 是逐分钟读数，本表是"事件"（开始/结束/幅度）。
"""
from sqlalchemy import (
    Column, Integer, BigInteger, Float, String, DateTime, Date,
    ForeignKey, Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class NocturnalSpO2Event(Base):
    __tablename__ = "nocturnal_spo2_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    night_date = Column(Date, nullable=False)
    start_ts = Column(DateTime(timezone=True), nullable=False)
    end_ts = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=False)

    min_spo2 = Column(Float, nullable=False)
    baseline_spo2 = Column(Float)
    drop_magnitude = Column(Float, nullable=False)  # 百分点

    concurrent_hr_delta = Column(Float)
    concurrent_respiration_rate = Column(Float)
    sleep_stage = Column(String)  # awake | light | deep | rem

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="nocturnal_spo2_events")

    __table_args__ = (
        Index('idx_nocturnal_events_user_night', 'user_id', 'night_date'),
        Index('idx_nocturnal_events_user_start', 'user_id', 'start_ts'),
    )
