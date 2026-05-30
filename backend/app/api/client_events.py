"""POST /api/v1/client-events — Mobile 侧埋点接入.

仅接受白名单事件, 避免垃圾数据. 旁路写, 失败不影响主流程.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.client_event import ClientEvent
from app.models.user import User

router = APIRouter(prefix="/client-events", tags=["client-events"])
logger = logging.getLogger(__name__)


# 白名单: 观察期看板需要跟踪的事件.
# Phase 0.4 (2026-05-04): 加 5 种核心事件解除"客户端埋点几乎为空" 的观察盲区.
# 同步 mobile/services/clientEvents.ts ClientEventName 类型定义.
_ALLOWED_EVENTS = frozenset({
    # 上一季 ship (2026-05-01)
    "reasoning_sheet_opened",
    "journal_timeline_entered",
    "specialist_scorecard_entered",
    # Phase 0.4 — 让看板看得见用户操作
    "home_chip_clicked",          # meta: { chip: 'trust_hero' | 'specialist', target? }
    "action_card_executed",       # meta: { card_id, action: 'execute' | 'complete' | 'reminder' }
    "push_notification_opened",   # meta: { kind, deep_link }
    "chat_message_sent",          # meta: { source: 'chat'|'voice'|'siri', has_image }
    "quick_record_logged",        # meta: { kind: 'bp'|'weight'|'water'|'medication'|... }
    # Phase 5 (2026-05-29) — starter chip CTR (调权从拍脑袋变成有据)
    "starter_chips_shown",        # meta: { keys: string[], source: 'chat' }  曝光(分母)
    "starter_chip_clicked",       # meta: { key, priority, position, source: 'chat' }  点击(分子)
})


class EventIn(BaseModel):
    event_name: str = Field(..., max_length=64)
    meta: Optional[Dict[str, Any]] = None

    @field_validator("meta")
    @classmethod
    def _meta_size_limit(cls, v: Optional[Dict[str, Any]]):
        if v is None:
            return v
        import json

        payload = json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > 2048:
            raise ValueError("meta too large (max 2KB)")
        return v


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
