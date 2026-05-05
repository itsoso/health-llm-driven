"""
GET  /api/v1/clarification/opener?alert_id=X       — voice-chat 进入时拉开场白
POST /api/v1/clarification/extract-memory          — voice-chat 关闭时抽 user turns 写 memory_facts
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required, get_db
from app.models.anomaly_alert import AnomalyAlert
from app.models.user import User
from app.services.alert_clarification import get_clarification_opener
from app.services.memory_dialog_extractor import extract_facts_from_dialog
from app.services.memory_service import write_fact

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


class ExtractMemoryRequest(BaseModel):
    user_turns: List[str]  # 用户在这次对话里说过的话, 按顺序
    alert_id: Optional[int] = None  # 关联的告警 (用 rationale 作为 context_hint)


class ExtractMemoryResponse(BaseModel):
    extracted_count: int
    facts: List[dict]


@router.post("/extract-memory", response_model=ExtractMemoryResponse)
async def extract_memory(
    payload: ExtractMemoryRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    voice-chat 结束时旁路调用 — 从用户 turns 抽 facts 写 memory_facts.
    Karpathy "anterograde amnesia" 解药: 让 AI 真正记住用户告诉它的事.

    幂等: write_fact 自动检测重复 → reinforce 而非新建
    失败安全: LLM 抽取失败返回空, 不抛异常 (不能让对话退出体验出错)
    """
    if not payload.user_turns:
        return ExtractMemoryResponse(extracted_count=0, facts=[])

    # 拼 user turns. 上限 800 字防止 LLM 上下文爆.
    text = "\n".join(t.strip() for t in payload.user_turns if t and t.strip())
    if not text:
        return ExtractMemoryResponse(extracted_count=0, facts=[])
    if len(text) > 800:
        text = text[-800:]  # 保留最近的对话

    # context_hint 来自 alert rationale, 让抽取更聚焦
    context_hint: Optional[str] = None
    if payload.alert_id:
        alert = db.query(AnomalyAlert).filter(
            AnomalyAlert.id == payload.alert_id,
            AnomalyAlert.user_id == current_user.id,
        ).first()
        if alert:
            tmpl = get_clarification_opener(alert)
            if tmpl:
                context_hint = tmpl.get("rationale")

    extracted = await extract_facts_from_dialog(text, context_hint=context_hint)
    if not extracted:
        return ExtractMemoryResponse(extracted_count=0, facts=[])

    # 写库
    written: List[dict] = []
    source = {
        "type": "voice_dialog",
        "alert_id": payload.alert_id,
        "user_turns_count": len(payload.user_turns),
    }
    for f in extracted:
        fact = write_fact(
            db,
            user_id=current_user.id,
            tier="episodic",  # 对话来的事实先放 episodic, lifecycle task 会自动升 semantic
            subject=f.subject,
            predicate=f.predicate,
            object_value=f.object_value,
            object_unit=f.object_unit,
            confidence=f.confidence,
            source=source,
        )
        if fact:
            written.append({
                "id": fact.id,
                "subject": fact.subject,
                "predicate": fact.predicate,
                "object_value": fact.object_value,
                "confidence": fact.confidence,
            })

    logger.info(
        f"[clarification.extract] user={current_user.id} alert={payload.alert_id} "
        f"extracted={len(extracted)} written={len(written)}"
    )
    return ExtractMemoryResponse(extracted_count=len(written), facts=written)
