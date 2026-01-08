"""健康打卡Schema"""
from pydantic import BaseModel
from datetime import date
from typing import Optional, Dict, Any, List


class HealthCheckinCreate(BaseModel):
    """创建健康打卡"""
    user_id: Optional[int] = None  # 后端使用当前登录用户ID
    checkin_date: date
    running_distance: Optional[float] = None
    running_duration: Optional[int] = None
    squats_count: Optional[int] = None
    leg_raises_count: Optional[int] = None  # 踢腿次数
    tai_chi_duration: Optional[int] = None
    ba_duan_jin_duration: Optional[int] = None
    other_exercises: Optional[Dict[str, Any]] = None
    # 鼻炎管理
    sneeze_count: Optional[int] = None  # 打喷嚏次数
    sneeze_times: Optional[List[Dict[str, Any]]] = None  # 打喷嚏时间记录
    nasal_wash_count: Optional[int] = None  # 洗鼻次数
    nasal_wash_times: Optional[List[Dict[str, Any]]] = None  # 洗鼻时间记录
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
    leg_raises_count: Optional[int] = None  # 踢腿次数
    tai_chi_duration: Optional[int]
    ba_duan_jin_duration: Optional[int]
    other_exercises: Optional[Dict[str, Any]]
    # 鼻炎管理
    sneeze_count: Optional[int] = None
    sneeze_times: Optional[List[Dict[str, Any]]] = None
    nasal_wash_count: Optional[int] = None
    nasal_wash_times: Optional[List[Dict[str, Any]]] = None
    daily_score: Optional[int]
    goals_completed: Optional[Dict[str, Any]]
    notes: Optional[str]
    personalized_advice: Optional[str]
    
    class Config:
        from_attributes = True

