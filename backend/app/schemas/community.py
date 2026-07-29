"""Contracts for the opt-in anonymous peer support surface."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ReactionType = Literal["support", "same_path", "learned"]


class CommunityPostCreate(BaseModel):
    source_type: Literal["diet_record"]
    source_id: int = Field(gt=0)
    caption: Optional[str] = Field(default=None, max_length=280)
    idempotency_key: str = Field(min_length=8, max_length=160)


class CommunityReactionUpdate(BaseModel):
    reaction: ReactionType


class CommunityReportCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=200)


class CommunityPostResponse(BaseModel):
    id: int
    anonymous_name: str
    source_type: str
    snapshot: dict[str, Any]
    caption: Optional[str]
    status: str
    reaction_counts: dict[str, int]
    my_reaction: Optional[ReactionType]
    is_owner: bool
    created_at: datetime


class CommunityFeedResponse(BaseModel):
    items: list[CommunityPostResponse]


class CommunityReportResponse(BaseModel):
    report_count: int
    status: str
