"""活动状态 Schemas"""
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field


class ActivityStatusCreate(BaseModel):
    status_text: str = Field(..., max_length=100)
    category: str = Field(..., pattern="^(studying|working|exercising|resting|entertainment|other)$")
    estimated_duration_minutes: Optional[int] = Field(None, ge=1, le=720)
    notes: Optional[str] = Field(None, max_length=500)


class ActivityStatusUpdate(BaseModel):
    status_text: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)


class ActivityStatusResponse(BaseModel):
    id: int
    user_id: int
    status_text: str
    category: str
    start_time: datetime
    estimated_duration_minutes: Optional[int] = None
    estimated_end_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ActivityTimelineItem(BaseModel):
    id: int
    status_text: str
    category: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    is_active: bool


class ActivityCategoryStats(BaseModel):
    category: str
    total_minutes: int
    count: int
    percentage: float


class ActivityStats(BaseModel):
    total_records: int = 0
    total_active_minutes: int = 0
    category_distribution: List[ActivityCategoryStats] = Field(default_factory=list)
    daily_timeline: List[ActivityTimelineItem] = Field(default_factory=list)
