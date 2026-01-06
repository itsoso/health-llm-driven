"""心率数据Schema"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class HeartRatePoint(BaseModel):
    """单个心率数据点"""
    timestamp: int = Field(..., description="时间戳（毫秒）")
    time: str = Field(..., description="时间（HH:MM格式）")
    value: int = Field(..., description="心率值（bpm）")


class HeartRateSummary(BaseModel):
    """心率每日汇总"""
    record_date: date
    avg_heart_rate: Optional[int] = Field(None, description="平均心率")
    max_heart_rate: Optional[int] = Field(None, description="最大心率")
    min_heart_rate: Optional[int] = Field(None, description="最小心率")
    resting_heart_rate: Optional[int] = Field(None, description="静息心率")


class HRVPoint(BaseModel):
    """单个HRV数据点"""
    timestamp: int = Field(..., description="时间戳（毫秒）")
    time: str = Field(..., description="时间（HH:MM格式）")
    value: float = Field(..., description="HRV值（ms）")


class DailyHeartRateResponse(BaseModel):
    """每日心率详细数据响应"""
    record_date: date
    summary: HeartRateSummary
    heart_rate_timeline: List[HeartRatePoint] = Field(default_factory=list, description="心率时间线数据")
    hrv: Optional[float] = Field(None, description="HRV值（夜间平均）")
    
    # 分析数据
    zones: Optional[Dict[str, int]] = Field(None, description="心率区间分布（分钟）")
    
    class Config:
        from_attributes = True


class HeartRateTrendResponse(BaseModel):
    """心率趋势数据响应（多天）"""
    days: int = Field(..., description="统计天数")
    daily_data: List[HeartRateSummary] = Field(default_factory=list)
    hrv_data: List[Dict[str, Any]] = Field(default_factory=list, description="每日HRV数据")
    
    # 统计数据
    avg_heart_rate: Optional[float] = Field(None, description="平均心率")
    avg_resting_heart_rate: Optional[float] = Field(None, description="平均静息心率")
    avg_hrv: Optional[float] = Field(None, description="平均HRV")
    max_heart_rate: Optional[int] = Field(None, description="最高心率")
    min_heart_rate: Optional[int] = Field(None, description="最低心率")
    
    class Config:
        from_attributes = True

