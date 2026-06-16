"""
GET /api/v1/timeline — 健康事件流 (H 产品改进).

聚合多源事件 (运动 / 告警 / 睡眠低分 / 用药 / 体检) 统一时间线倒序.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required, get_db
from app.models.user import User
from app.services.events_timeline_service import build_timeline
from app.services.today_timeline_service import build_today_spine

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


# ===== 统一今日时间线(首页新脊柱)=====

class CompleteRef(BaseModel):
    object_type: str
    object_id: int


class ProofRef(BaseModel):
    metric: str
    label: str
    delta: str
    direction: Optional[str] = None
    association_only: bool = True  # 时序关联,非因果(PRD R9)


class TodaySpineItem(BaseModel):
    id: str
    kind: str  # action / checkup / advisory / outcome / observation
    time_window: str
    title: str
    subtitle: Optional[str] = None
    icon: str
    color: str
    status: Optional[str] = None
    priority: int
    can_complete: bool
    complete_ref: Optional[CompleteRef] = None
    deep_link: Optional[str] = None
    severity: Optional[str] = None
    proof: Optional[ProofRef] = None


class TodayPast(BaseModel):
    completed_count: int
    events: List[TodaySpineItem]


class TodayCounts(BaseModel):
    actionable: int
    overdue: int
    info: int


class TodaySpineResponse(BaseModel):
    date: str
    current_window: str  # morning|noon|afternoon|evening|bedtime|anytime
    items: List[TodaySpineItem]
    past: TodayPast
    counts: TodayCounts


@router.get("/today", response_model=TodaySpineResponse)
def get_today_spine(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """统一今日时间线:未来该做(议程)+ 今日已发生(观测)+ 结果归因。

    只读投影,组合 agenda_service + events_timeline_service。完成动作走 /agenda/complete。
    强制 user_id 隔离(PRD §7 不变量)。
    """
    return build_today_spine(db, current_user.id)


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
