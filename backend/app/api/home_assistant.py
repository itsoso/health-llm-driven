"""Home Assistant 集成 API —— 事件摄入 (inbound, 设计文档 §9/§10).

本 PR 范围只有 inbound webhook (HA automation 事件上行). 命令下行 (scene/script)
和连通性测试 (/test) 是后续需要 HA 凭证的 PR.

用户隔离: Depends(get_current_user_required), user_id 一律取 current_user.id,
绝不从 body 取. 隐私 (§11): 卧室自动化事件不进通用 LLM (见 bedroom_environment_service).
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.schemas.bedroom_environment import BedroomEventIn
from app.services import bedroom_environment_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/integrations/home-assistant", tags=["home-assistant"]
)


@router.post("/webhook")
async def ingest_automation_event(
    data: BedroomEventIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """摄入一条 HA 自动化事件 → 落 BedroomAutomationEvent + 旁路写 AuditLog.

    摄入失败 (DB 写入) 上抛 500, 让客户端感知, 不假装成功 (对齐地基 PR).
    event_type 缺失 → 400 (不静默写垃圾行).
    """
    try:
        event = svc.record_event(
            db, current_user.id, data.model_dump(exclude_none=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        # service 已 log + rollback; 摄入失败让客户端感知, 不假装成功.
        raise HTTPException(status_code=500, detail="卧室自动化事件写入失败")
    return {
        "id": event.id,
        "room_id": event.room_id,
        "event_type": event.event_type,
        "source": event.source,
        "audit_ref": event.audit_ref,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
