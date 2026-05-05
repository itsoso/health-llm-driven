"""
GET /api/v1/clarification/opener?alert_id=X

mobile voice-chat ?intent=clarify&alert_id=X 进入时调本 API 拿 AI 开场白.
返回 opener 字段供 TTS 播放, rationale 字段供后续 LLM context.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required, get_db
from app.models.anomaly_alert import AnomalyAlert
from app.models.user import User
from app.services.alert_clarification import get_clarification_opener

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clarification", tags=["clarification"])


class ClarificationOpenerResponse(BaseModel):
    opener: str
    rationale: str
    alert_type: str
    alert_id: int


@router.get("/opener", response_model=ClarificationOpenerResponse)
def get_opener(
    alert_id: int = Query(..., description="anomaly_alert.id"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    alert = db.query(AnomalyAlert).filter(
        AnomalyAlert.id == alert_id,
        AnomalyAlert.user_id == current_user.id,
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")

    result = get_clarification_opener(alert)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"告警类型 {alert.alert_type} 暂无 clarify 模板",
        )
    return ClarificationOpenerResponse(**result)
