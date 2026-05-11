"""conversation_memory API —— Phase 3 P3-3: chat opener "我记得你 X"."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.conversation_memory_service import get_top_memory_for_opener

router = APIRouter(prefix="/conversation-memory", tags=["conversation-memory"])

_TYPE_LABELS = {
    "medical": "医嘱",
    "allergy": "过敏",
    "preference": "偏好",
    "instruction": "注意事项",
    "fact": "个人情况",
}


@router.get("/opener", summary="拉 top 1-2 条记忆给会诊页 opener")
def get_opener_memories(
    k: int = Query(2, ge=1, le=3, description="拉几条 (默认 2, 上限 3)"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """供 mobile 会诊 tab 进入时调用 — 拉用户最相关的 1-2 条 active 记忆,
    在第一条 AI 消息前显示 "我记得你: <X>" 给用户感知持久记忆.

    优先级: allergy > medical > preference > 其他.
    失败 (无记忆 / 异常) 返回空 list, mobile 端不显示 opener.
    """
    try:
        memories = get_top_memory_for_opener(db, current_user.id, k=k)
    except Exception:
        return {"items": []}

    items: List[Dict[str, Any]] = []
    for m in memories:
        items.append(
            {
                "id": m.id,
                "type": m.memory_type,
                "type_label": _TYPE_LABELS.get(m.memory_type, "记忆"),
                "content": m.content,
            }
        )
    return {"items": items}
