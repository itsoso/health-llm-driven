"""体重追踪模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class WeightRecord(Base):
    """体重记录"""
    __tablename__ = "weight_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    weight = Column(Float, nullable=False)  # 体重 (kg)
    body_fat_percentage = Column(Float)  # 体脂率 (%)
    muscle_mass = Column(Float)  # 肌肉量 (kg)
    bmi = Column(Float)  # BMI
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="weight_records")

