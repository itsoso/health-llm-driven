"""视觉API使用记录"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class VisionUsageLog(Base):
    """视觉API每日使用记录"""
    __tablename__ = "vision_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    usage_date = Column(Date, nullable=False)
    usage_type = Column(String(20), nullable=False)  # "beauty" or "recognize"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_vision_usage_user_date', 'user_id', 'usage_date'),
    )
