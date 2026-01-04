"""每日建议Schema"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, Dict, Any


class DailyRecommendationCreate(BaseModel):
    """创建每日建议"""
    user_id: int
    recommendation_date: date
    analysis_date: date
    one_day_recommendation: Optional[Dict[str, Any]] = None
    seven_day_recommendation: Optional[Dict[str, Any]] = None


class DailyRecommendationResponse(BaseModel):
    """每日建议响应"""
    id: int
    user_id: int
    recommendation_date: date
    analysis_date: date
    one_day_recommendation: Optional[Dict[str, Any]]
    seven_day_recommendation: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

