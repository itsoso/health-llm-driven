"""交互反馈 Schema"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


# ---- 请求 ----

class FeedbackCreateRequest(BaseModel):
    """用户提交反馈（👍👎）"""
    conversation_type: str = Field(..., pattern="^(chat|agent)$")
    conversation_id: int
    message_id: int
    rating: int = Field(..., ge=1, le=5)  # 1=👎, 5=👍
    feedback_text: Optional[str] = None


class FeedbackImplicitRequest(BaseModel):
    """后端自动记录隐式信号"""
    conversation_type: str = Field(..., pattern="^(chat|agent)$")
    conversation_id: int
    message_id: int
    skill_used: Optional[str] = None
    skill_version: Optional[str] = None
    implicit_signal: Optional[str] = None
    success: Optional[bool] = None
    error_type: Optional[str] = None
    response_time_ms: Optional[int] = None


# ---- 响应 ----

class FeedbackResponse(BaseModel):
    id: int
    rating: Optional[int] = None
    feedback_text: Optional[str] = None
    skill_used: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillMetricsResponse(BaseModel):
    skill_name: str
    skill_version: str
    date: datetime
    total_calls: int
    success_rate: Optional[float] = None
    avg_rating: Optional[float] = None
    thumbs_up: int
    thumbs_down: int
    is_production: bool
    is_canary: bool

    model_config = ConfigDict(from_attributes=True)


class SkillPerformanceSummary(BaseModel):
    """单个 Skill 的性能概览"""
    skill_name: str
    current_version: str
    total_calls_7d: int
    success_rate_7d: Optional[float] = None
    avg_rating_7d: Optional[float] = None
    thumbs_up_7d: int
    thumbs_down_7d: int
    has_canary: bool
    canary_version: Optional[str] = None


class OptimizationLogResponse(BaseModel):
    id: int
    skill_name: str
    old_version: str
    new_version: str
    trigger: str
    analysis: Optional[str] = None
    changes_summary: Optional[str] = None
    status: str
    old_success_rate: Optional[float] = None
    new_success_rate: Optional[float] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
