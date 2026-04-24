"""Workout 心率区间分布（P1a）。

来源：garminconnect.get_activity_hr_in_timezones(activity_id)
用途：MovementCoach 判断训练类型（Z2 有氧基础 / Z4+ 高强度 / Z5 冲刺）
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class WorkoutHrZone(Base):
    __tablename__ = "workout_hr_zones"

    id = Column(Integer, primary_key=True, index=True)
    workout_id = Column(Integer, ForeignKey("workout_records.id", ondelete="CASCADE"), nullable=False)

    zone_index = Column(Integer, nullable=False)  # 1..5
    zone_name = Column(String)  # "Zone 1" / "Easy" / ...
    lower_bpm = Column(Integer)
    upper_bpm = Column(Integer)
    seconds_in_zone = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_workout_hr_zones_workout', 'workout_id'),
    )
