"""基础健康数据模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class BasicHealthData(Base):
    """个人基础健康数据"""
    __tablename__ = "basic_health_data"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 基础数据
    height = Column(Float)  # 身高 (cm)
    weight = Column(Float)  # 体重 (kg)
    bmi = Column(Float)  # 身体质量指数
    
    # 血压
    systolic_bp = Column(Integer)  # 收缩压
    diastolic_bp = Column(Integer)  # 舒张压
    
    # 血脂
    total_cholesterol = Column(Float)  # 总胆固醇 (mmol/L)
    ldl_cholesterol = Column(Float)  # 低密度脂蛋白胆固醇
    hdl_cholesterol = Column(Float)  # 高密度脂蛋白胆固醇
    triglycerides = Column(Float)  # 甘油三酯
    
    # 其他基础指标
    blood_glucose = Column(Float)  # 血糖 (mmol/L)
    body_fat_percentage = Column(Float)  # 体脂率 (%)
    muscle_mass = Column(Float)  # 肌肉量 (kg)
    
    # 记录日期
    record_date = Column(Date, nullable=False)
    
    # 备注
    notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="basic_health_records")

