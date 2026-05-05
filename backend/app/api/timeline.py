"""
GET /api/v1/timeline — 健康事件流 (H 产品改进).

聚合多源事件 (运动 / 告警 / 睡眠低分 / 用药 / 体检) 统一时间线倒序.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required, get_db
from app.models.user import User
from app.services.events_timeline_service import build_timeline

router = APIRouter(prefix="/timeline", tags=["timeline"])


class TimelineEventResponse(BaseModel):
    id: str
    source: str
    title: str
    subtitle: Optional[str] = None
    icon: str
    color: str
    occurred_at: str  # ISO datetime
    deep_link: Optional[str] = None
    severity: Optional[str] = None


class TimelineResponse(BaseModel):
    events: List[TimelineEventResponse]
    days: int
    count: int


@router.get("", response_model=TimelineResponse)
def get_timeline(
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=40, ge=1, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    events = build_timeline(db, current_user.id, days=days, limit=limit)
    return TimelineResponse(
        events=[
            TimelineEventResponse(
                id=e.id,
                source=e.source,
                title=e.title,
                subtitle=e.subtitle,
                icon=e.icon,
                color=e.color,
                occurred_at=e.occurred_at.isoformat(),
                deep_link=e.deep_link,
                severity=e.severity,
            )
            for e in events
        ],
        days=days,
        count=len(events),
    )
