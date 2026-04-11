"""
GET /api/v1/twin/me —— Digital Health Twin 端点。

返回当前用户的完整健康状态视图。供前端和所有上层 agent 共享。
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.twin.builder import build_twin
from app.twin.cache import (
    TWIN_CACHE_TTL_SECONDS,
    get_cached_twin,
    invalidate_twin,
    set_cached_twin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twin", tags=["twin"])


@router.get("/me")
def get_my_twin(
    fresh: bool = Query(False, description="强制重新构建，忽略缓存"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """
    当前用户的 Digital Health Twin（生理/身体/化验/药物/基因/环境/行为/心理/目标/慢病）。

    - 默认命中缓存（5 分钟 TTL）
    - `fresh=true` 强制重新构建
    - 返回结构：`{meta, physiological, body_composition, labs, medication, supplement,
       genetic, environment, behavioral, mental, chronic, goals, freshness}`
    """
    user_id = current_user.id

    if not fresh:
        cached = get_cached_twin(user_id)
        if cached is not None:
            cached.setdefault("meta", {})
            cached["meta"]["cache_status"] = "hit"
            return cached

    twin = build_twin(db, user_id)
    payload = twin.model_dump(mode="json")
    payload.setdefault("meta", {})
    payload["meta"]["cache_status"] = "miss"

    set_cached_twin(user_id, payload, ttl=TWIN_CACHE_TTL_SECONDS)
    return payload


@router.post("/me/invalidate")
def invalidate_my_twin(
    current_user: User = Depends(get_current_user_required),
):
    """手动使缓存失效。通常由数据写入路径在后台调用，这里给调试用。"""
    invalidate_twin(current_user.id)
    return {"message": "twin cache invalidated", "user_id": current_user.id}
