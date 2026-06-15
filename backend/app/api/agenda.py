"""统一健康议程 API(R1)。只读投影:今日该做什么,一处可见、跨端一致。"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services import agenda_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agenda", tags=["统一健康议程"])


@router.get("/today")
async def agenda_today(
    followup_within_days: int = Query(default=14, le=120),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """今日统一议程:三域协议待办 + 近 N 天到期复查,按优先级排序。"""
    return agenda_service.today(db, current_user.id, followup_within_days)


@router.get("/range")
async def agenda_range(
    days: int = Query(default=7, le=120),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """区间视图:常驻每日协议 + 窗口内按到期日排布的复查。"""
    return agenda_service.range_view(db, current_user.id, days)


class AgendaComplete(BaseModel):
    object_type: str            # health_protocol(其余来源后续接通)
    object_id: int
    track: str = "protocol"     # protocol / manual
    value: Optional[Dict[str, Any]] = None


@router.post("/complete")
async def agenda_complete(
    data: AgendaComplete,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """统一完成路由:按来源类型路由到对应 source 的完成(写真实业务记录)。"""
    try:
        return agenda_service.complete_item(
            db, current_user.id, data.object_type, data.object_id, data.track, data.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
