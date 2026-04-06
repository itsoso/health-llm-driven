"""按摩/理疗追踪模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class MassageRecord(Base):
    """按摩/理疗记录"""
    __tablename__ = "massage_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False, index=True)
    start_time = Column(String(5))   # HH:MM
    duration_minutes = Column(Integer)  # 时长（分钟）

    # 地点
    location_name = Column(String(200))  # 店名，如"一指禅"
    location_address = Column(String(500))  # 地址，如"文一西路xxx号"

    # 按摩信息
    massage_type = Column(String(50), default="推拿")  # 推拿/盲人按摩/足疗/正骨/刮痧/拔罐/艾灸等
    therapist = Column(String(100))  # 师傅编号或姓名，如"6号师傅"
    body_parts = Column(String(500))  # 部位：颈椎/背部/腰部/全身等（逗号分隔）

    # 费用
    price = Column(Float)  # 费用（元）

    # 问题与效果
    issues_before = Column(Text)  # 按摩前的问题，如"左边睡觉压脖子"
    treatment_notes = Column(Text)  # 按摩过程记录，如"纠正了左边睡觉压脖子的问题，背部肌肉放松"
    feeling_after = Column(Text)  # 按摩后感受，如"全身轻松，非常有效果"
    rating = Column(Integer)  # 满意度 1-5

    notes = Column(Text)  # 其他备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="massage_records")
