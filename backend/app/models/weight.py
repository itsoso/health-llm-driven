"""体重与身体成分追踪模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class WeightRecord(Base):
    """体重与身体成分记录"""
    __tablename__ = "weight_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False, index=True)
    weight = Column(Float, nullable=False)  # 体重 (kg)
    body_fat_percentage = Column(Float)  # 体脂率 (%)
    muscle_mass_kg = Column(Float)  # 肌肉量 (kg) - 数据库字段名
    source = Column(String(50))  # 数据来源

    # 扩展身体成分字段
    visceral_fat = Column(Integer)       # 内脏脂肪等级 (1-30)
    bone_mass_kg = Column(Float)         # 骨量 (kg)
    water_percentage = Column(Float)     # 水分率 (%)
    bmi = Column(Float)                  # BMI 指数
    bmr = Column(Integer)               # 基础代谢率 (kcal)
    metabolic_age = Column(Integer)      # 代谢年龄
    subcutaneous_fat = Column(Float)     # 皮下脂肪率 (%)
    skeletal_muscle_pct = Column(Float)  # 骨骼肌率 (%)
    protein_pct = Column(Float)          # 蛋白质率 (%)

    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="weight_records")

    # 为了兼容前端，添加属性别名
    @property
    def muscle_mass(self):
        return self.muscle_mass_kg

    @muscle_mass.setter
    def muscle_mass(self, value):
        self.muscle_mass_kg = value
