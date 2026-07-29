"""体检数据Schema"""
from pydantic import BaseModel, ConfigDict
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
    # 兼容旧客户端;服务端始终以登录用户为准。
    user_id: Optional[int] = None
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
    source: Optional[str] = None
    manually_corrected_at: Optional[datetime] = None
    original_value: Optional[float] = None
    original_value_text: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MedicalExamItemUpdate(BaseModel):
    """Calibrate UI — 用户手工校正 OCR 抽错的值. 所有字段可选, 只改传入的部分."""
    item_name: Optional[str] = None
    value: Optional[float] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    is_abnormal: Optional[str] = None  # normal/abnormal/high/low
    notes: Optional[str] = None


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

    model_config = ConfigDict(from_attributes=True)


class MedicalExamReportSummary(BaseModel):
    """体检/检查报告级列表摘要,用于 Agent 报告清单,不包含全量 item 明细。"""
    id: int
    exam_date: date
    exam_type: Optional[str] = None
    body_system: Optional[str] = None
    hospital_name: Optional[str] = None
    doctor_name: Optional[str] = None
    overall_assessment: Optional[str] = None
    conclusions_count: int = 0
    items_count: int = 0
    abnormal_items_count: int = 0
    created_at: Optional[datetime] = None
