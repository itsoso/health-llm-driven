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
    muscle_mass_kg = Column(Float)  # 肌肉量 (kg) - 数据库字段名
    bmi = Column(Float)  # BMI
    source = Column(String(50))  # 数据来源
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # updated_at 字段在数据库中不存在
    
    user = relationship("User", backref="weight_records")
    
    # 为了兼容前端，添加属性别名
    @property
    def muscle_mass(self):
        return self.muscle_mass_kg
    
    @muscle_mass.setter
    def muscle_mass(self, value):
        self.muscle_mass_kg = value

