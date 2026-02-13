"""用药管理模型"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Text, Boolean, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Medication(Base):
    """药品定义"""
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(200), nullable=False)  # 药品名称
    dosage = Column(String(100))  # 用量（如 400mg）
    frequency = Column(String(100))  # 服用频率描述（如 每日2次）
    times_per_day = Column(Integer, default=1)  # 每日次数
    reminder_times = Column(JSON)  # 提醒时间 ["08:00", "20:00"]
    category = Column(String(50))  # 分类：处方药/非处方药/保健品
    purpose = Column(String(200))  # 用途/适应症
    side_effects = Column(Text)  # 已知副作用
    interactions = Column(Text)  # 药物相互作用提醒

    start_date = Column(Date)  # 开始服用日期
    end_date = Column(Date)  # 计划结束日期
    is_active = Column(Boolean, default=True)  # 是否在服用中

    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="medications")
    logs = relationship("MedicationLog", back_populates="medication", lazy="dynamic")

    __table_args__ = (
        Index("ix_medications_user_active", "user_id", "is_active"),
    )


class MedicationLog(Base):
    """服药记录"""
    __tablename__ = "medication_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    medication_id = Column(Integer, ForeignKey("medications.id"), nullable=False)

    taken_date = Column(Date, nullable=False)  # 服药日期
    taken_time = Column(String(10))  # 服药时间 "08:00"
    status = Column(String(20), nullable=False, default="taken")  # taken / skipped / delayed
    skip_reason = Column(String(200))  # 跳过原因
    actual_dosage = Column(String(100))  # 实际用量（如果与标准不同）
    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="medication_logs")
    medication = relationship("Medication", back_populates="logs")

    __table_args__ = (
        Index("ix_medication_logs_user_date", "user_id", "taken_date"),
        Index("ix_medication_logs_med_date", "medication_id", "taken_date"),
    )
