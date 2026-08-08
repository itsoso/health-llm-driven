"""当前病症追踪 Pydantic Schemas"""
from datetime import date, datetime
from typing import Optional, List
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(from_attributes=True)


class IllnessEpisodeCreate(BaseModel):
    # 弱模型 tool-calling 常把字段写成 illness_name、漏 start_date —— 接受别名 + 默认今天,
    # 避免 422(name Field required)。规范字段仍是 name(见 SKILL.md)。
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(..., max_length=100,
                      validation_alias=AliasChoices("name", "illness_name"))
    start_date: date = Field(default_factory=date.today)
    severity: Optional[int] = Field(None, ge=1, le=10)
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
    severity: Optional[int]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class IllnessEpisodeResponse(IllnessEpisodeListResponse):
    updates: List[IllnessUpdateResponse] = []
