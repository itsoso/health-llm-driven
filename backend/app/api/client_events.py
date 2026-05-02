"""POST /api/v1/client-events — Mobile 侧埋点接入.

仅接受白名单事件, 避免垃圾数据. 旁路写, 失败不影响主流程.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.client_event import ClientEvent
from app.models.user import User

router = APIRouter(prefix="/client-events", tags=["client-events"])
logger = logging.getLogger(__name__)


# 白名单: 观察期看板需要跟踪的事件.
_ALLOWED_EVENTS = frozenset({
    "reasoning_sheet_opened",
    "journal_timeline_entered",
    "specialist_scorecard_entered",
})


class EventIn(BaseModel):
    event_name: str = Field(..., max_length=64)
    meta: Optional[Dict[str, Any]] = None


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="上报一条 UI 事件")
def post_client_event(
    body: EventIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if body.event_name not in _ALLOWED_EVENTS:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"event_name 不在白名单: {body.event_name}",
                "allowed": sorted(_ALLOWED_EVENTS),
            },
        )

    try:
        ev = ClientEvent(
            user_id=current_user.id,
            event_name=body.event_name,
            meta=body.meta,
        )
        db.add(ev)
        db.commit()
        return {"ok": True, "id": ev.id}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[client-events] 写入失败 (bypass): {e}")
        try:
            db.rollback()
        except Exception:
            pass
        # 不抛 500 — 埋点失败不影响用户主流程
        return {"ok": False}
