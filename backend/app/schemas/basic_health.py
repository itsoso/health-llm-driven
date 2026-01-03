"""基础健康数据Schema"""
from pydantic import BaseModel
from datetime import date
from typing import Optional


class BasicHealthDataCreate(BaseModel):
    """创建基础健康数据"""
    user_id: int
    height: Optional[float] = None
    weight: Optional[float] = None
    bmi: Optional[float] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    total_cholesterol: Optional[float] = None
    ldl_cholesterol: Optional[float] = None
    hdl_cholesterol: Optional[float] = None
    triglycerides: Optional[float] = None
    blood_glucose: Optional[float] = None
    body_fat_percentage: Optional[float] = None
    muscle_mass: Optional[float] = None
    record_date: date
    notes: Optional[str] = None


class BasicHealthDataResponse(BaseModel):
    """基础健康数据响应"""
    id: int
    user_id: int
    height: Optional[float]
    weight: Optional[float]
    bmi: Optional[float]
    systolic_bp: Optional[int]
    diastolic_bp: Optional[int]
    total_cholesterol: Optional[float]
    ldl_cholesterol: Optional[float]
    hdl_cholesterol: Optional[float]
    triglycerides: Optional[float]
    blood_glucose: Optional[float]
    body_fat_percentage: Optional[float]
    muscle_mass: Optional[float]
    record_date: date
    notes: Optional[str]
    
    class Config:
        from_attributes = True

