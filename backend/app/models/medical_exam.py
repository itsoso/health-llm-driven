"""体检数据模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class BodySystem(str, enum.Enum):
    """身体系统分类"""
    NERVOUS = "nervous"  # 神经系统
    CIRCULATORY = "circulatory"  # 循环系统
    RESPIRATORY = "respiratory"  # 呼吸系统
    DIGESTIVE = "digestive"  # 消化系统
    URINARY = "urinary"  # 泌尿系统
    ENDOCRINE = "endocrine"  # 内分泌系统
    IMMUNE = "immune"  # 免疫系统
    SKELETAL = "skeletal"  # 骨骼系统
    MUSCULAR = "muscular"  # 肌肉系统
    OTHER = "other"  # 其他


class ExamType(str, enum.Enum):
    """体检类型"""
    BLOOD_ROUTINE = "blood_routine"  # 血常规
    LIPID_PROFILE = "lipid_profile"  # 血脂相关
    URINE_ROUTINE = "urine_routine"  # 尿常规
    IMMUNE = "immune"  # 免疫相关
    LIVER_FUNCTION = "liver_function"  # 肝功能
    KIDNEY_FUNCTION = "kidney_function"  # 肾功能
    THYROID = "thyroid"  # 甲状腺功能
    OTHER = "other"  # 其他


class MedicalExam(Base):
    """体检记录"""
    __tablename__ = "medical_exams"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    exam_date = Column(Date, nullable=False)  # 体检日期
    exam_type = Column(Enum(ExamType), nullable=False)  # 体检类型
    body_system = Column(Enum(BodySystem))  # 所属身体系统
    hospital_name = Column(String)  # 医院名称
    doctor_name = Column(String)  # 医生姓名
    
    # 总体评价
    overall_assessment = Column(Text)  # 总体评价
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="medical_exams")
    items = relationship("MedicalExamItem", back_populates="exam", cascade="all, delete-orphan")


class MedicalExamItem(Base):
    """体检项目明细"""
    __tablename__ = "medical_exam_items"
    
    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("medical_exams.id"), nullable=False)
    
    item_name = Column(String, nullable=False)  # 项目名称
    item_code = Column(String)  # 项目代码
    value = Column(Float)  # 检测值
    unit = Column(String)  # 单位
    reference_range = Column(String)  # 参考范围
    result = Column(String)  # 结果（正常/异常/偏高/偏低）
    
    # 异常标记
    is_abnormal = Column(String, default="normal")  # normal/abnormal/high/low
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    exam = relationship("MedicalExam", back_populates="items")

