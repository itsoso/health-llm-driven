"""女性健康模型"""
import logging
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

logger = logging.getLogger(__name__)


class MenstrualCycle(Base):
    """经期周期记录"""
    __tablename__ = "menstrual_cycles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    start_date = Column(Date, nullable=False)  # 周期开始日期
    end_date = Column(Date)  # 经期结束日期
    cycle_length = Column(Integer)  # 周期长度（天）
    period_length = Column(Integer)  # 经期持续天数
    flow_intensity = Column(String(20))  # 经量：light / moderate / heavy
    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="menstrual_cycles")
    symptoms = relationship("CycleSymptom", back_populates="cycle", lazy="dynamic")

    __table_args__ = (
        Index("ix_menstrual_cycles_user_start", "user_id", "start_date"),
    )


class CycleSymptom(Base):
    """周期症状记录"""
    __tablename__ = "cycle_symptoms"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cycle_id = Column(Integer, ForeignKey("menstrual_cycles.id"))

    record_date = Column(Date, nullable=False)  # 记录日期
    symptom_type = Column(String(50), nullable=False)  # 症状类型：cramps/headache/bloating/mood_swing/fatigue/breast_tenderness
    severity = Column(Integer, default=1)  # 严重程度 1-5
    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="cycle_symptoms")
    cycle = relationship("MenstrualCycle", back_populates="symptoms")

    __table_args__ = (
        Index("ix_cycle_symptoms_user_date", "user_id", "record_date"),
        Index("ix_cycle_symptoms_cycle", "cycle_id"),
    )
