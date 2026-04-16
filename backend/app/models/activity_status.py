"""活动状态数据模型"""
from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ActivityStatus(Base):
    """用户当前活动状态记录"""
    __tablename__ = "activity_statuses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    status_text = Column(String(100), nullable=False)       # 活动名称，如"学习"、"工作"
    category = Column(String(50), nullable=False)            # studying/working/exercising/resting/entertainment/other

    start_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    estimated_duration_minutes = Column(Integer, nullable=True)
    estimated_end_time = Column(DateTime(timezone=True), nullable=True)
    actual_end_time = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    user = relationship("User", backref="activity_statuses")

    __table_args__ = (
        Index('idx_activity_status_user_active', 'user_id', 'is_active'),
        Index('idx_activity_status_user_start', 'user_id', 'start_time'),
    )
