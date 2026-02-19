"""当前病症追踪 Pydantic Schemas"""
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class IllnessUpdateCreate(BaseModel):
    update_date: date
    severity: Optional[int] = Field(None, ge=1, le=10)
    status: Optional[str] = None  # active/improving/resolved
    notes: Optional[str] = None


class IllnessUpdateResponse(BaseModel):
    id: int
    episode_id: int
    update_date: date
    severity: Optional[int]
    status: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class IllnessEpisodeCreate(BaseModel):
    name: str = Field(..., max_length=100)
    start_date: date
    severity: int = Field(5, ge=1, le=10)
    status: str = Field("active")
    notes: Optional[str] = None


class IllnessEpisodePatch(BaseModel):
    severity: Optional[int] = Field(None, ge=1, le=10)
    status: Optional[str] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None


class IllnessEpisodeListResponse(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: Optional[date]
    status: str
    severity: int
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class IllnessEpisodeResponse(IllnessEpisodeListResponse):
    updates: List[IllnessUpdateResponse] = []
