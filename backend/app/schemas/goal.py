"""目标管理Schema"""
from pydantic import BaseModel
from datetime import date
from typing import Optional
from app.models.goal import GoalType, GoalPeriod, GoalStatus


class GoalCreate(BaseModel):
    """创建目标"""
    user_id: int
    goal_type: GoalType
    goal_period: GoalPeriod
    title: str
    description: Optional[str] = None
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    implementation_steps: Optional[str] = None
    status: Optional[GoalStatus] = GoalStatus.ACTIVE
    priority: Optional[int] = 5
    notes: Optional[str] = None


class GoalResponse(BaseModel):
    """目标响应"""
    id: int
    user_id: int
    goal_type: GoalType
    goal_period: GoalPeriod
    title: str
    description: Optional[str]
    target_value: Optional[float]
    target_unit: Optional[str]
    current_value: Optional[float]
    start_date: date
    end_date: Optional[date]
    implementation_steps: Optional[str]
    status: GoalStatus
    priority: Optional[int]
    notes: Optional[str]
    
    class Config:
        from_attributes = True


class GoalProgressCreate(BaseModel):
    """创建目标进展"""
    goal_id: int
    progress_date: date
    progress_value: Optional[float] = None
    completion_percentage: Optional[float] = None
    notes: Optional[str] = None

