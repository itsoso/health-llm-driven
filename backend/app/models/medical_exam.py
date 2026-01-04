"""体检数据模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, Enum, JSON
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
    COMPREHENSIVE = "comprehensive"  # 综合体检
    OTHER = "other"  # 其他


class MedicalExam(Base):
    """体检记录"""
    __tablename__ = "medical_exams"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 患者信息
    patient_name = Column(String)  # 患者姓名
    patient_gender = Column(String)  # 性别
    patient_age = Column(Integer)  # 年龄
    exam_number = Column(String)  # 体检号
    
    exam_date = Column(Date, nullable=False)  # 体检日期
    exam_type = Column(String, default="other")  # 体检类型（改为String以支持更多类型）
    body_system = Column(String)  # 所属身体系统
    hospital_name = Column(String)  # 医院名称
    doctor_name = Column(String)  # 医生姓名
    
    # 总体评价
    overall_assessment = Column(Text)  # 总体评价摘要
    conclusions = Column(JSON)  # 详细结论列表 [{category, title, description, recommendations}]
    
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
    
    # 检查类别
    category = Column(String)  # blood_routine/liver_function/kidney_function/lipid/immune/thyroid/ultrasound/ct/ecg/eye/ent/body_composition/other
    
    item_name = Column(String, nullable=False)  # 项目名称
    item_code = Column(String)  # 项目代码
    value = Column(Float)  # 检测值（数值型）
    value_text = Column(Text)  # 检测值（文本型，用于影像结论等）
    unit = Column(String)  # 单位
    reference_range = Column(String)  # 参考范围
    result = Column(String)  # 结果（正常/异常/偏高/偏低）
    
    # 异常标记
    is_abnormal = Column(String, default="normal")  # normal/abnormal/high/low
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    exam = relationship("MedicalExam", back_populates="items")

