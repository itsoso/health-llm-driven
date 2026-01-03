"""健康打卡Schema"""
from pydantic import BaseModel
from datetime import date
from typing import Optional, Dict, Any


class HealthCheckinCreate(BaseModel):
    """创建健康打卡"""
    user_id: int
    checkin_date: date
    running_distance: Optional[float] = None
    running_duration: Optional[int] = None
    squats_count: Optional[int] = None
    tai_chi_duration: Optional[int] = None
    ba_duan_jin_duration: Optional[int] = None
    other_exercises: Optional[Dict[str, Any]] = None
    daily_score: Optional[int] = None
    goals_completed: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    personalized_advice: Optional[str] = None


class HealthCheckinResponse(BaseModel):
    """健康打卡响应"""
    id: int
    user_id: int
    checkin_date: date
    running_distance: Optional[float]
    running_duration: Optional[int]
    squats_count: Optional[int]
    tai_chi_duration: Optional[int]
    ba_duan_jin_duration: Optional[int]
    other_exercises: Optional[Dict[str, Any]]
    daily_score: Optional[int]
    goals_completed: Optional[Dict[str, Any]]
    notes: Optional[str]
    personalized_advice: Optional[str]
    
    class Config:
        from_attributes = True

