"""习惯追踪 Schemas"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


# 习惯定义
class HabitDefinitionBase(BaseModel):
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    target_frequency: str = "daily"
    target_count: int = 1
    is_active: bool = True
    sort_order: int = 0


class HabitDefinitionCreate(HabitDefinitionBase):
    user_id: int


class HabitDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    target_frequency: Optional[str] = None
    target_count: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class HabitDefinitionResponse(HabitDefinitionBase):
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 习惯打卡记录
class HabitRecordBase(BaseModel):
    record_date: date
    completed: bool = False
    notes: Optional[str] = None


class HabitRecordCreate(HabitRecordBase):
    habit_id: int
    user_id: int


class HabitRecordResponse(HabitRecordBase):
    id: int
    habit_id: int
    user_id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 批量打卡请求
class HabitBatchCheckin(BaseModel):
    user_id: int
    record_date: date
    checkins: List[dict]  # [{"habit_id": 1, "completed": true}, ...]


# 带记录的习惯响应
class HabitWithRecord(BaseModel):
    habit: HabitDefinitionResponse
    record: Optional[HabitRecordResponse] = None
    streak: int = 0  # 连续打卡天数


# 习惯统计
class HabitStats(BaseModel):
    habit_id: int
    habit_name: str
    total_days: int
    completed_days: int
    completion_rate: float
    current_streak: int
    longest_streak: int

