"""健康趋势预测 Schema"""
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List, Dict, Any


class TrendDimensionSummary(BaseModel):
    """单维度趋势摘要"""
    dimension: str
    period: str
    trend_direction: Optional[str] = None
    insights: Optional[List[str]] = None
    suggestions: Optional[List[str]] = None
    risk_alerts: Optional[List[str]] = None
    report_date: date


class TrendLatestResponse(BaseModel):
    """最新趋势概览响应"""
    report_date: Optional[date] = None
    dimensions: List[TrendDimensionSummary]


class TrendDetailResponse(BaseModel):
    """趋势详细报告响应"""
    id: int
    user_id: int
    report_date: date
    dimension: str
    period: str
    trend_direction: Optional[str] = None
    raw_data_summary: Optional[Dict[str, Any]] = None
    insights: Optional[List[str]] = None
    suggestions: Optional[List[str]] = None
    risk_alerts: Optional[List[str]] = None
    full_report: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TrendHistoryResponse(BaseModel):
    """历史报告列表响应"""
    items: List[TrendDetailResponse]
    total: int
