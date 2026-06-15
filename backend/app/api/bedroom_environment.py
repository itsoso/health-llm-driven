"""卧室环境快照 API (设计文档 §9 地基).

只读 + 摄入. HA Adapter / 场景下行 / Protocol / UI 是后续 PR.

用户隔离: 全部 Depends(get_current_user_required), user_id 一律取 current_user.id,
绝不从 body 取. 隐私 (§11): 这些数据不进通用 LLM (见 bedroom_environment_service).
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.schemas.bedroom_environment import BedroomSnapshotIn
from app.services import bedroom_environment_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/environment/bedroom", tags=["bedroom-environment"])


@router.post("/snapshots")
async def ingest_snapshot(
    data: BedroomSnapshotIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """摄入一条卧室环境快照 (HA / 任意客户端推)."""
    try:
        row = svc.record_snapshot(
            db, current_user.id, data.model_dump(exclude_none=True)
        )
    except Exception:
        # service 已 log + rollback; 摄入失败让客户端感知, 不假装成功.
        raise HTTPException(status_code=500, detail="卧室环境快照写入失败")
    return {
        "id": row.id,
        "room_id": row.room_id,
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
    }


@router.get("/current")
async def get_current_snapshot(
    room_id: str = Query(default="bedroom"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Optional[Dict[str, Any]]:
    """当前 (最近一条) 卧室环境快照, 含 stale 判定. 无数据返回 null."""
    return svc.get_current(db, current_user.id, room_id)


@router.get("/history")
async def get_snapshot_history(
    days: int = Query(default=7, ge=1, le=90),
    room_id: str = Query(default="bedroom"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """近 N 天卧室环境快照, 时间倒序."""
    return svc.get_history(db, current_user.id, room_id, days)
