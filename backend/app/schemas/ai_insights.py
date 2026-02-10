"""AI 洞察相关的 Schema"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, Dict, Any


# ========== AI 每日洞察 ==========
class AIInsightBase(BaseModel):
    """AI 洞察基础模型"""
    review_date: date
    content: str
    summary: Optional[str] = None


class AIInsightCreate(AIInsightBase):
    """创建 AI 洞察"""
    user_id: int
    health_snapshot: Optional[Dict[str, Any]] = None


class AIInsightResponse(AIInsightBase):
    """AI 洞察响应"""
    id: int
    user_id: int
    health_snapshot: Optional[Dict[str, Any]] = None
    generated_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class AIInsightListResponse(BaseModel):
    """AI 洞察列表响应"""
    items: list[AIInsightResponse]
    total: int


# ========== 实时建议 ==========
class RealtimeRecommendationBase(BaseModel):
    """实时建议基础模型"""
    content: str
    recommendation_type: Optional[str] = None
    priority: Optional[str] = "medium"


class RealtimeRecommendationCreate(RealtimeRecommendationBase):
    """创建实时建议"""
    user_id: int
    context_data: Optional[Dict[str, Any]] = None
    location: Optional[Dict[str, Any]] = None
    weather_data: Optional[Dict[str, Any]] = None
    air_quality_data: Optional[Dict[str, Any]] = None


class RealtimeRecommendationResponse(RealtimeRecommendationBase):
    """实时建议响应"""
    id: int
    user_id: int
    context_data: Optional[Dict[str, Any]] = None
    location: Optional[Dict[str, Any]] = None
    weather_data: Optional[Dict[str, Any]] = None
    air_quality_data: Optional[Dict[str, Any]] = None
    generated_at: datetime
    expires_at: Optional[datetime] = None
    is_active: int

    class Config:
        from_attributes = True


# ========== 请求模型 ==========
class GenerateRecommendationRequest(BaseModel):
    """生成实时建议请求"""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None


class WeatherContext(BaseModel):
    """天气上下文"""
    temperature: Optional[float] = None
    feels_like: Optional[float] = None
    humidity: Optional[int] = None
    weather_condition: Optional[str] = None
    weather_description: Optional[str] = None
    wind_speed: Optional[float] = None


class AirQualityContext(BaseModel):
    """空气质量上下文"""
    aqi: Optional[int] = None
    pm25: Optional[float] = None
    pm10: Optional[float] = None
    quality_level: Optional[str] = None
