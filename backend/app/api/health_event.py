"""健康事件流 API"""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.health_event_service import HealthEventService
from app.schemas.health_event import (
    HealthEventIngest,
    HealthEventConfirm,
    HealthEventResponse,
    BatchConfirmRequest,
    PendingEventsSummary,
    EventSourceCreate,
    EventSourceUpdate,
    EventSourceResponse,
)

async def get_user_id_from_any_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    current_user: User = Depends(get_current_user_required),
) -> int:
    """Return the identity authorized by the shared JWT/API-key policy."""
    del x_api_key  # Declares the supported header; shared auth performs validation.
    return current_user.id

router = APIRouter(prefix="/health-events", tags=["health-events"])


# ========== 事件摄入 ==========

@router.post("/ingest", response_model=HealthEventResponse)
async def ingest_event(
    request: HealthEventIngest,
    user_id: int = Depends(get_user_id_from_any_auth),
    db: Session = Depends(get_db),
):
    """
    摄入一个健康事件（来自设备/NFC/手动触发）。

    支持两种认证方式：
    - Bearer Token（JWT）：小程序/App 使用
    - X-API-Key：NFC 快捷指令/Siri/外部系统使用（长期有效）
    """
    service = HealthEventService(db)
    event = service.ingest_event(
        user_id=user_id,
        event_type=request.event_type,
        source=request.source,
        raw_data=request.raw_data,
        source_device_id=request.source_device_id,
        event_time=request.event_time,
    )
    return HealthEventResponse.model_validate(event)


# ========== 待确认事件 ==========

@router.get("/pending", response_model=PendingEventsSummary)
def get_pending_events(
    event_type: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取待确认的健康事件"""
    service = HealthEventService(db)
    summary = service.get_pending_summary(current_user.id)
    events = service.get_pending_events(current_user.id, event_type, limit)
    return PendingEventsSummary(
        total=summary["total"],
        by_type=summary["by_type"],
        events=[HealthEventResponse.model_validate(e) for e in events],
    )


# ========== 确认/修正/忽略 ==========

@router.patch("/{event_id}/confirm", response_model=HealthEventResponse)
def confirm_event(
    event_id: int,
    request: HealthEventConfirm,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """确认、修正或忽略一个健康事件"""
    service = HealthEventService(db)
    try:
        event = service.confirm_event(
            user_id=current_user.id,
            event_id=event_id,
            confirmed_data=request.confirmed_data,
            status=request.status.value,
        )
        return HealthEventResponse.model_validate(event)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/batch-confirm", response_model=List[HealthEventResponse])
def batch_confirm_events(
    request: BatchConfirmRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """批量确认事件（接受 AI 推理结果）"""
    service = HealthEventService(db)
    events = service.batch_confirm(current_user.id, request.event_ids)
    return [HealthEventResponse.model_validate(e) for e in events]


# ========== 事件历史 ==========

@router.get("/history", response_model=List[HealthEventResponse])
def get_event_history(
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """查询事件历史"""
    service = HealthEventService(db)
    events = service.get_events(current_user.id, event_type, status, limit)
    return [HealthEventResponse.model_validate(e) for e in events]


# ========== EventSource 管理 ==========

@router.post("/sources", response_model=EventSourceResponse)
def create_event_source(
    request: EventSourceCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """注册事件来源（NFC标签/蓝牙设备等）"""
    service = HealthEventService(db)
    source = service.create_source(
        user_id=current_user.id,
        source_type=request.source_type,
        device_id=request.device_id,
        name=request.name,
        event_type=request.event_type,
        config=request.config,
        auto_confirm_threshold=request.auto_confirm_threshold,
    )
    return EventSourceResponse.model_validate(source)


@router.get("/sources", response_model=List[EventSourceResponse])
def get_event_sources(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取用户的所有事件来源"""
    service = HealthEventService(db)
    sources = service.get_sources(current_user.id)
    return [EventSourceResponse.model_validate(s) for s in sources]


@router.put("/sources/{source_id}", response_model=EventSourceResponse)
def update_event_source(
    source_id: int,
    request: EventSourceUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新事件来源"""
    service = HealthEventService(db)
    try:
        source = service.update_source(
            user_id=current_user.id,
            source_id=source_id,
            update_data=request.model_dump(exclude_unset=True),
        )
        return EventSourceResponse.model_validate(source)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/sources/{source_id}")
def delete_event_source(
    source_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除事件来源"""
    service = HealthEventService(db)
    try:
        service.delete_source(current_user.id, source_id)
        return {"message": "删除成功"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
