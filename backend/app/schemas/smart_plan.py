from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class PlanItemResponse(BaseModel):
    id: int
    day_of_week: int
    category: str
    title: str
    description: Optional[str] = None
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    checkin_template_id: Optional[int] = None
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    sort_order: int = 0

    class Config:
        from_attributes = True


class WeeklyPlanResponse(BaseModel):
    id: int
    user_id: int
    week_start: date
    status: str
    focus_areas: List[str] = []
    weekly_summary: Optional[str] = None
    completion_rate: float = 0.0
    ai_model: Optional[str] = None
    user_feedback: Optional[int] = None
    items: List[PlanItemResponse] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WeeklyPlanListItem(BaseModel):
    id: int
    week_start: date
    status: str
    focus_areas: List[str] = []
    completion_rate: float = 0.0
    user_feedback: Optional[int] = None
    item_count: int = 0
    completed_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class GeneratePlanRequest(BaseModel):
    target_week: str = Field("current", description="'current' 或 'next'")


class PlanItemUpdate(BaseModel):
    is_completed: bool


class PlanFeedbackRequest(BaseModel):
    score: int = Field(..., ge=1, le=5, description="评分 1-5")
