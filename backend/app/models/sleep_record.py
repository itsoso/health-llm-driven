"""手动睡眠记录数据模型"""
from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Boolean, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class SleepRecord(Base):
    """手动睡眠记录（非Garmin用户）"""
    __tablename__ = "sleep_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 记录日期（醒来的日期）
    record_date = Column(Date, nullable=False, index=True)

    # 睡眠时间段
    bedtime = Column(DateTime(timezone=True), nullable=False)
    wake_time = Column(DateTime(timezone=True), nullable=False)

    # 睡眠质量 1-5
    sleep_quality = Column(Integer, nullable=False)

    # 计算字段
    total_duration_minutes = Column(Integer, nullable=True)

    # 夜醒次数
    wake_count = Column(Integer, nullable=True, default=0)

    # 做梦
    had_dream = Column(Boolean, nullable=True, default=False)
    dream_description = Column(Text, nullable=True)

    # 入睡难度 1-5
    fall_asleep_difficulty = Column(Integer, nullable=True)

    # 醒后感觉 1-5
    morning_feeling = Column(Integer, nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    user = relationship("User", backref="sleep_records")

    __table_args__ = (
        Index('idx_sleep_user_date', 'user_id', 'record_date'),
    )
