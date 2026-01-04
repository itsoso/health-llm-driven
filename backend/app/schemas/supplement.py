"""补剂管理 Schemas"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, time, datetime


# 补剂定义
class SupplementDefinitionBase(BaseModel):
    name: str
    dosage: Optional[str] = None
    timing: Optional[str] = None  # morning/noon/evening/bedtime
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class SupplementDefinitionCreate(SupplementDefinitionBase):
    user_id: int


class SupplementDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    dosage: Optional[str] = None
    timing: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class SupplementDefinitionResponse(SupplementDefinitionBase):
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 补剂打卡记录
class SupplementRecordBase(BaseModel):
    record_date: date
    taken: bool = False
    taken_time: Optional[time] = None
    notes: Optional[str] = None


class SupplementRecordCreate(SupplementRecordBase):
    supplement_id: int
    user_id: int


class SupplementRecordResponse(SupplementRecordBase):
    id: int
    supplement_id: int
    user_id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 批量打卡请求
class SupplementBatchCheckin(BaseModel):
    user_id: int
    record_date: date
    checkins: List[dict]  # [{"supplement_id": 1, "taken": true}, ...]


# 带记录的补剂响应
class SupplementWithRecord(BaseModel):
    supplement: SupplementDefinitionResponse
    record: Optional[SupplementRecordResponse] = None

