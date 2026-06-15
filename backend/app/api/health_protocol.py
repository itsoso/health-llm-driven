"""健康协议层 API(P1 第一刀)。双轨录入:协议轨 ✓ / 手工轨,均写同一事件流。"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services import health_protocol_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/protocols", tags=["健康协议层"])


class ProtocolCreate(BaseModel):
    domain: str
    name: str
    mechanism: Optional[str] = None
    implied_quantity: Optional[Dict[str, Any]] = None
    cadence: str = "daily"
    time_window: str = "anytime"
    completion_mode: str = "one_tap"
    can_default_complete: bool = False
    manual_track_allowed: bool = True
    program_id: Optional[int] = None
    source_model: Optional[str] = None
    notes: Optional[str] = None


class ProtocolComplete(BaseModel):
    track: str = "protocol"            # protocol / manual
    value: Optional[Dict[str, Any]] = None


class ProtocolSkip(BaseModel):
    reason: Optional[str] = None       # SKIP_REASONS 之一


@router.post("")
async def create_protocol(
    data: ProtocolCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        p = svc.create_protocol(db, current_user.id, data.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.serialize_protocol(p)


@router.get("/me")
async def list_my_protocols(
    active_only: bool = True,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return [svc.serialize_protocol(p) for p in svc.list_protocols(db, current_user.id, active_only)]


@router.get("/today")
async def today(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """今日协议待办 + 完成态(双轨任一轨完成都算)。"""
    return svc.today_status(db, current_user.id)


@router.post("/seed/water-cup")
async def seed_water_cup(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """快速建一个 2000ml 温水杯协议(参考实现)。"""
    return svc.serialize_protocol(svc.create_water_cup_protocol(db, current_user.id))


@router.post("/{protocol_id}/complete")
async def complete(
    protocol_id: int,
    data: ProtocolComplete,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        ev = svc.complete_protocol(db, protocol_id, current_user.id, track=data.track, value=data.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if ev is None:
        raise HTTPException(status_code=404, detail="协议不存在")
    return {"protocol_id": protocol_id, "status": ev.status, "track": ev.track, "event_date": str(ev.event_date)}


@router.post("/{protocol_id}/skip")
async def skip(
    protocol_id: int,
    data: ProtocolSkip,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        ev = svc.skip_protocol(db, protocol_id, current_user.id, reason=data.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if ev is None:
        raise HTTPException(status_code=404, detail="协议不存在")
    return {"protocol_id": protocol_id, "status": ev.status, "skip_reason": ev.skip_reason, "event_date": str(ev.event_date)}


@router.post("/{protocol_id}/archive")
async def archive(
    protocol_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if not svc.archive_protocol(db, protocol_id, current_user.id):
        raise HTTPException(status_code=404, detail="协议不存在")
    return {"protocol_id": protocol_id, "status": "archived"}
