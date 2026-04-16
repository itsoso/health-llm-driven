"""情绪追踪数据模型"""
from datetime import UTC, date, datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, Index, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class MoodRecord(Base):
    """情绪记录"""
    __tablename__ = "mood_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 记录日期和时间
    record_date = Column(Date, nullable=False, index=True)
    record_time = Column(DateTime(timezone=True), server_default=func.now())

    # 情绪评分 1-5: 1=很差, 2=较差, 3=一般, 4=较好, 5=很好
    mood_score = Column(Integer, nullable=False)

    # 情绪标签（多选），如 ["开心", "焦虑", "平静", "疲惫"]
    mood_tags = Column(JSON, default=list)

    # 精力等级 1-5
    energy_level = Column(Integer, nullable=True)

    # 压力等级 1-5
    stress_level = Column(Integer, nullable=True)

    # 焦虑等级 1-5
    anxiety_level = Column(Integer, nullable=True)

    # 睡眠质量 1-5（主观评价，补充 Garmin 客观数据）
    sleep_quality = Column(Integer, nullable=True)

    # 情绪日记/简短文字记录
    journal = Column(Text, nullable=True)

    # 触发因素（多选），如 ["工作", "运动", "社交", "天气"]
    triggers = Column(JSON, default=list)

    # 应对方式（多选），如 ["运动", "冥想", "社交", "音乐"]
    coping_methods = Column(JSON, default=list)

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # 关系
    user = relationship("User", backref="mood_records")

    __table_args__ = (
        Index('idx_mood_user_date', 'user_id', 'record_date'),
        Index('idx_mood_user_score', 'user_id', 'mood_score'),
    )
