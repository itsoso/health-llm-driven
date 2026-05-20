"""Daily Plan action event schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


DailyPlanActionEventType = Literal[
    "suggested",
    "accepted",
    "adjusted",
    "completed",
    "skipped",
    "verified",
]


class DailyPlanActionEventRequest(BaseModel):
    event_type: DailyPlanActionEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    plan_date: date | None = Field(default=None, description="默认今天")


class DailyPlanActionEventResponse(BaseModel):
    id: int
    plan_id: int | None
    plan_date: date
    action_id: str
    action_title: str
    event_type: DailyPlanActionEventType
    action_state: str
    payload: dict[str, Any]
