"""
Garmin 时间序列采样模型（P1a）

夜间/日间多种生理信号的逐分钟/逐段时序数据，供 SpO2 根因分析与其他下游 specialist 消费。
沿用现有 heart_rate_samples / spo2_samples 的 per-metric 表风格。
"""
from sqlalchemy import (
    Column, Integer, BigInteger, Float, String, DateTime, Date, Time,
    ForeignKey, Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class RespirationSample(Base):
    """睡眠/清醒期间呼吸频率采样（brpm，约每分钟一个点）。

    来源：garminconnect.get_respiration_data() → respirationValuesArray
    用途：夜间 SpO2 根因分析 —— 呼吸节律异常与氧降事件对齐
    """
    __tablename__ = "respiration_samples"

    # Integer in ORM for SQLite-compat; DB migration uses BIGSERIAL
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False)
    sample_time = Column(Time, nullable=False)
    respiration_rate = Column(Float, nullable=False)  # brpm
    epoch_ms = Column(BigInteger)

    source = Column(String, default="garmin")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="respiration_samples")

    __table_args__ = (
        Index('idx_resp_user_date', 'user_id', 'record_date'),
        Index('idx_resp_user_date_time', 'user_id', 'record_date', 'sample_time'),
    )


class HrvReading(Base):
    """HRV 夜间时序读数（RMSSD ms，约每 5 分钟一个点）。

    来源：garminconnect.get_hrv_data() → hrvReadings
    用途：RecoveryCoach 用真时序替代日均做 baseline；SpO2 根因分析的自主神经证据
    """
    __tablename__ = "hrv_readings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False)
    reading_time = Column(Time, nullable=False)
    hrv_value = Column(Float, nullable=False)  # RMSSD ms
    reading_type = Column(String)  # nightly | 5min_avg | instantaneous
    epoch_ms = Column(BigInteger)

    source = Column(String, default="garmin")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="hrv_readings")

    __table_args__ = (
        Index('idx_hrv_user_date', 'user_id', 'record_date'),
        Index('idx_hrv_user_date_time', 'user_id', 'record_date', 'reading_time'),
    )


class StressSample(Base):
    """压力水平逐分钟采样（0-100，-1/-2 表示无数据/休息）。

    来源：garminconnect.get_stress_data() / get_all_day_stress()
    用途：MentalHealthCompanion 识别应激峰值；SpO2 根因分析的自主神经背景
    """
    __tablename__ = "stress_samples"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False)
    sample_time = Column(Time, nullable=False)
    stress_value = Column(Integer, nullable=False)  # 0-100 or -1/-2
    epoch_ms = Column(BigInteger)

    source = Column(String, default="garmin")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="stress_samples")

    __table_args__ = (
        Index('idx_stress_user_date', 'user_id', 'record_date'),
        Index('idx_stress_user_date_time', 'user_id', 'record_date', 'sample_time'),
    )
