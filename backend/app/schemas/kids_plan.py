"""Kids每日计划 schemas"""
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class PlanItemSchema(BaseModel):
    id: str
    emoji: str
    text: str
    done: bool = False
    startTime: Optional[str] = None
    endTime: Optional[str] = None


class KidsPlanSaveRequest(BaseModel):
    items: List[PlanItemSchema]


class KidsPlanResponse(BaseModel):
    plan_date: date
    items: List[PlanItemSchema]
    awarded_tier: int = 0
    points_awarded: int = 0  # 本次请求新增的积分
    total_kids_points: int = 0  # 用户当前总积分

    model_config = ConfigDict(from_attributes=True)


class KidsPlanCopyRequest(BaseModel):
    from_date: date
    to_date: date


# ===== 历史回顾 & AI 复盘 =====

class KidsPlanDaySummary(BaseModel):
    """每天摘要"""
    plan_date: date
    total_items: int
    done_count: int
    completion_rate: float  # 0.0 ~ 1.0
    awarded_tier: int = 0


class KidsPlanHistoryResponse(BaseModel):
    """历史统计响应"""
    range: str
    start_date: date
    end_date: date
    days: List[KidsPlanDaySummary]
    total_plan_days: int
    total_items: int
    total_done: int
    avg_completion_rate: float
    current_streak: int
    best_streak: int
    top_activities: List[dict]  # [{emoji, text, count}]


class KidsPlanReviewRequest(BaseModel):
    """AI 复盘请求"""
    range: str = "week"  # week | month | year


class KidsPlanReviewResponse(BaseModel):
    """AI 复盘响应"""
    range: str
    start_date: date
    end_date: date
    review_text: str
    stats_summary: dict
