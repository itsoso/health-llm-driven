"""排泄记录数据模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, Time, ForeignKey, Text, Boolean, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ExcretionRecord(Base):
    """排泄记录（大便/小便）"""
    __tablename__ = "excretion_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False, index=True)
    record_time = Column(Time, nullable=True)

    # 类型: bowel(大便) / urine(小便)
    type = Column(String(10), nullable=False)

    # === 大便字段 ===
    stool_type = Column(Integer, nullable=True)       # Bristol量表 1-7
    color = Column(String(20), nullable=True)          # brown/yellow/green/black/red/pale
    amount = Column(String(10), nullable=True)         # small/medium/large
    duration_minutes = Column(Integer, nullable=True)
    blood_present = Column(Boolean, nullable=True, default=False)

    # === 小便字段 ===
    urine_color = Column(String(20), nullable=True)    # transparent/light_yellow/yellow/dark_yellow/amber/brown/red
    urine_amount = Column(String(10), nullable=True)   # small/medium/large

    # === 共用字段 ===
    urgency = Column(Integer, nullable=True)           # 1-5
    pain_level = Column(Integer, nullable=True)        # 0-5
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="excretion_records")

    __table_args__ = (
        Index('idx_excretion_user_date', 'user_id', 'record_date'),
        Index('idx_excretion_user_date_type', 'user_id', 'record_date', 'type'),
    )
