"""体检数据Schema"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List, Any


class MedicalExamItemCreate(BaseModel):
    """创建体检项目"""
    category: Optional[str] = None  # 检查类别
    item_name: str
    item_code: Optional[str] = None
    value: Optional[float] = None
    value_text: Optional[str] = None  # 文本型检测值
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    result: Optional[str] = None
    is_abnormal: Optional[str] = "normal"
    notes: Optional[str] = None


class MedicalExamCreate(BaseModel):
    """创建体检记录"""
    user_id: int
    patient_name: Optional[str] = None
    patient_gender: Optional[str] = None
    patient_age: Optional[int] = None
    exam_number: Optional[str] = None
    exam_date: date
    exam_type: Optional[str] = "other"  # 改为字符串类型
    body_system: Optional[str] = None  # 改为字符串类型
    hospital_name: Optional[str] = None
    doctor_name: Optional[str] = None
    overall_assessment: Optional[str] = None
    conclusions: Optional[List[Any]] = None  # 结论列表
    notes: Optional[str] = None
    items: Optional[List[MedicalExamItemCreate]] = []


class MedicalExamItemResponse(BaseModel):
    """体检项目响应"""
    id: int
    category: Optional[str] = None
    item_name: str
    item_code: Optional[str] = None
    value: Optional[float] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    result: Optional[str] = None
    is_abnormal: Optional[str] = None
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class MedicalExamResponse(BaseModel):
    """体检记录响应"""
    id: int
    user_id: int
    patient_name: Optional[str] = None
    patient_gender: Optional[str] = None
    patient_age: Optional[int] = None
    exam_number: Optional[str] = None
    exam_date: date
    exam_type: Optional[str] = None  # 改为字符串类型
    body_system: Optional[str] = None  # 改为字符串类型
    hospital_name: Optional[str] = None
    doctor_name: Optional[str] = None
    overall_assessment: Optional[str] = None
    conclusions: Optional[List[Any]] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    items: List[MedicalExamItemResponse] = []
    
    class Config:
        from_attributes = True

