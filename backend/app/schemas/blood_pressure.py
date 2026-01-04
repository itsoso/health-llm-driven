"""血压追踪模式"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, time


class BloodPressureRecordBase(BaseModel):
    """血压记录基础"""
    record_date: date
    record_time: Optional[time] = None
    systolic: int  # 收缩压
    diastolic: int  # 舒张压
    pulse: Optional[int] = None  # 脉搏
    measurement_position: Optional[str] = None  # 测量姿势
    arm: Optional[str] = None  # 测量手臂
    notes: Optional[str] = None


class BloodPressureRecordCreate(BloodPressureRecordBase):
    """创建血压记录"""
    user_id: int


class BloodPressureRecordUpdate(BaseModel):
    """更新血压记录"""
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    pulse: Optional[int] = None
    measurement_position: Optional[str] = None
    arm: Optional[str] = None
    notes: Optional[str] = None


class BloodPressureRecordResponse(BloodPressureRecordBase):
    """血压记录响应"""
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # 血压分类
    category: Optional[str] = None

    class Config:
        from_attributes = True


class BloodPressureStats(BaseModel):
    """血压统计"""
    average_systolic: Optional[float] = None
    average_diastolic: Optional[float] = None
    average_pulse: Optional[float] = None
    highest_systolic: Optional[int] = None
    lowest_systolic: Optional[int] = None
    highest_diastolic: Optional[int] = None
    lowest_diastolic: Optional[int] = None
    total_records: int = 0
    normal_count: int = 0  # 正常次数
    elevated_count: int = 0  # 偏高次数
    high_count: int = 0  # 高血压次数

