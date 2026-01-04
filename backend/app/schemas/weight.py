"""体重追踪模式"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class WeightRecordBase(BaseModel):
    """体重记录基础"""
    record_date: date
    weight: float
    body_fat_percentage: Optional[float] = None
    muscle_mass: Optional[float] = None
    bmi: Optional[float] = None
    notes: Optional[str] = None


class WeightRecordCreate(WeightRecordBase):
    """创建体重记录"""
    user_id: int


class WeightRecordUpdate(BaseModel):
    """更新体重记录"""
    weight: Optional[float] = None
    body_fat_percentage: Optional[float] = None
    muscle_mass: Optional[float] = None
    bmi: Optional[float] = None
    notes: Optional[str] = None


class WeightRecordResponse(WeightRecordBase):
    """体重记录响应"""
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WeightStats(BaseModel):
    """体重统计"""
    current_weight: Optional[float] = None
    target_weight: Optional[float] = None
    highest_weight: Optional[float] = None
    lowest_weight: Optional[float] = None
    average_weight: Optional[float] = None
    weight_change_30d: Optional[float] = None  # 30天变化
    total_records: int = 0

