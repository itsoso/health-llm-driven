"""疾病记录Schema"""
from pydantic import BaseModel
from datetime import date
from typing import Optional


class DiseaseRecordCreate(BaseModel):
    """创建疾病记录"""
    user_id: int
    disease_name: str
    icd_code: Optional[str] = None
    diagnosis_date: date
    hospital_name: Optional[str] = None
    department: Optional[str] = None
    doctor_name: Optional[str] = None
    diagnosis_description: Optional[str] = None
    symptoms: Optional[str] = None
    severity: Optional[str] = None
    treatment_plan: Optional[str] = None
    medications: Optional[str] = None
    status: Optional[str] = "active"
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    notes: Optional[str] = None


class DiseaseRecordResponse(BaseModel):
    """疾病记录响应"""
    id: int
    user_id: int
    disease_name: str
    icd_code: Optional[str]
    diagnosis_date: date
    hospital_name: Optional[str]
    department: Optional[str]
    doctor_name: Optional[str]
    diagnosis_description: Optional[str]
    symptoms: Optional[str]
    severity: Optional[str]
    treatment_plan: Optional[str]
    medications: Optional[str]
    status: Optional[str]
    follow_up_date: Optional[date]
    follow_up_notes: Optional[str]
    notes: Optional[str]
    
    class Config:
        from_attributes = True

