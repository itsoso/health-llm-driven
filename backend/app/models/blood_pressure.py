"""血压追踪模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, Time
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class BloodPressureRecord(Base):
    """血压记录"""
    __tablename__ = "blood_pressure_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    record_time = Column(Time)  # 测量时间
    
    systolic = Column(Integer, nullable=False)  # 收缩压 (mmHg)
    diastolic = Column(Integer, nullable=False)  # 舒张压 (mmHg)
    pulse = Column(Integer)  # 脉搏 (次/分)
    
    measurement_position = Column(String)  # 测量姿势（坐/卧/站）
    arm = Column(String)  # 测量手臂（左/右）
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="blood_pressure_records")

