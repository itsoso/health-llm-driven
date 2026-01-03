"""体检数据Schema"""
from pydantic import BaseModel
from datetime import date
from typing import Optional, List
from app.models.medical_exam import ExamType, BodySystem


class MedicalExamItemCreate(BaseModel):
    """创建体检项目"""
    item_name: str
    item_code: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    result: Optional[str] = None
    is_abnormal: Optional[str] = "normal"
    notes: Optional[str] = None


class MedicalExamCreate(BaseModel):
    """创建体检记录"""
    user_id: int
    exam_date: date
    exam_type: ExamType
    body_system: Optional[BodySystem] = None
    hospital_name: Optional[str] = None
    doctor_name: Optional[str] = None
    overall_assessment: Optional[str] = None
    notes: Optional[str] = None
    items: Optional[List[MedicalExamItemCreate]] = []


class MedicalExamItemResponse(BaseModel):
    """体检项目响应"""
    id: int
    item_name: str
    item_code: Optional[str]
    value: Optional[float]
    unit: Optional[str]
    reference_range: Optional[str]
    result: Optional[str]
    is_abnormal: Optional[str]
    notes: Optional[str]
    
    class Config:
        from_attributes = True


class MedicalExamResponse(BaseModel):
    """体检记录响应"""
    id: int
    user_id: int
    exam_date: date
    exam_type: ExamType
    body_system: Optional[BodySystem]
    hospital_name: Optional[str]
    doctor_name: Optional[str]
    overall_assessment: Optional[str]
    notes: Optional[str]
    items: List[MedicalExamItemResponse] = []
    
    class Config:
        from_attributes = True

