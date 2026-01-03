"""疾病记录模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class DiseaseRecord(Base):
    """疾病记录"""
    __tablename__ = "disease_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 疾病信息
    disease_name = Column(String, nullable=False)  # 疾病名称
    icd_code = Column(String)  # ICD编码
    diagnosis_date = Column(Date, nullable=False)  # 诊断日期
    
    # 医院信息
    hospital_name = Column(String)  # 医院名称
    department = Column(String)  # 科室
    doctor_name = Column(String)  # 医生姓名
    
    # 诊断信息
    diagnosis_description = Column(Text)  # 诊断描述
    symptoms = Column(Text)  # 症状
    severity = Column(String)  # 严重程度（轻度/中度/重度）
    
    # 治疗方案
    treatment_plan = Column(Text)  # 治疗方案
    medications = Column(Text)  # 用药情况
    
    # 状态
    status = Column(String, default="active")  # active/cured/chronic/improving
    
    # 随访信息
    follow_up_date = Column(Date)  # 随访日期
    follow_up_notes = Column(Text)  # 随访记录
    
    notes = Column(Text)  # 其他备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="disease_records")

