"""
GET /api/v1/timeline — 健康事件流 (H 产品改进).

聚合多源事件 (运动 / 告警 / 睡眠低分 / 用药 / 体检) 统一时间线倒序.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
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
    # 归因项带完整 metric/label/delta;简报/异常这类纯洞察项只带 association_only。
    metric: Optional[str] = None
    label: Optional[str] = None
    delta: Optional[str] = None
    direction: Optional[str] = None
    association_only: bool = True  # 时序关联,非因果(PRD R9)


class TodaySpineItem(BaseModel):
    id: str
    kind: str  # action / checkup / advisory / outcome / observation / insight
    time_window: str
    title: str
    subtitle: Optional[str] = None
    icon: str
    color: str
    status: Optional[str] = None
    priority: int
    can_complete: bool
    complete_ref: Optional[CompleteRef] = None
    # 物化后的 first-class HealthEvent id —— 客户端用它调闭环完成端点。
    event_id: Optional[int] = None
    action_kind: Optional[str] = None
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

    只读投影,组合 agenda_service + events_timeline_service。完成动作走
    POST /timeline/events/{id}/complete(闭环:翻 HealthEvent 生命周期 + 双轨回写)。
    强制 user_id 隔离(PRD §7 不变量)。
    """
    return build_today_spine(db, current_user.id)


# ===== 闭环完成端点(把脊柱项熄灭的唯一写路径)=====

class CompleteAgendaEventRequest(BaseModel):
    status: str = Field(default="done", description="done | skipped")
    skip_reason: Optional[str] = Field(
        default=None,
        description="status=skipped 时可带:no_time/forgot/no_supply/too_tired/"
                    "wrong_place/too_hard/unwell/social",
    )


class SourceWriteRef(BaseModel):
    object_type: str
    object_id: int
    status: Optional[str] = None
    track: Optional[str] = None


class CompleteAgendaEventResponse(BaseModel):
    event_id: int
    agenda_status: str  # done | skipped
    action_kind: Optional[str] = None
    title: Optional[str] = None
    skip_reason: Optional[str] = None
    completed_at: Optional[str] = None
    complete_ref: Optional[CompleteRef] = None
    idempotent: bool  # True = 已是终态(双击/重放),本次无二次回写
    source_write: Optional[SourceWriteRef] = None


@router.post("/events/{event_id}/complete", response_model=CompleteAgendaEventResponse)
def complete_agenda_event(
    event_id: int,
    request: CompleteAgendaEventRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """闭环完成一个议程 HealthEvent(THE fix)。

    翻 HealthEvent 生命周期 (pending → done|skipped) **并** 经 agenda_service.complete_item
    双轨回写真实 source(用药/协议/...)。幂等(双击 → 一次效果)。强制 user_id 隔离
    (跨用户 → 404)。回写失败 → 422,不假装成功。
    """
    from app.services import timeline_agenda_service as tas

    try:
        result = tas.complete_agenda_event(
            db, current_user.id, event_id,
            status=request.status, skip_reason=request.skip_reason,
        )
    except tas.AgendaEventNotFound:
        raise HTTPException(status_code=404, detail="议程事件不存在")
    except LookupError:
        # 回写来源(协议/药)已不存在 / 非本人 → 404(complete_item 对 not-found 抛 LookupError)。
        raise HTTPException(status_code=404, detail="完成来源不存在")
    except tas.AgendaCompleteError as e:
        # 真实 source 回写失败 → 让客户端感知(不静默吞、不假装完成)。
        raise HTTPException(status_code=422, detail=f"完成回写失败: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CompleteAgendaEventResponse(**result)


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
