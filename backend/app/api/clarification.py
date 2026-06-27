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
from app.services.personal_models.intervention_priors import gate_text_for_clinician

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clarification", tags=["clarification"])

# 因果有效性裁决谓词 —— 提及药物混杂指标时必须降级为描述性 observed_change (R4)。
# responds_to / does_not_respond_to 都是"X 对 Y 有效/无效"的因果断言; partially 同理。
_CAUSAL_EFFICACY_PREDICATES = frozenset(
    {"responds_to", "does_not_respond_to", "partially_responds_to"}
)


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
    demoted_count = 0
    source = {
        "type": "voice_dialog",
        "alert_id": payload.alert_id,
        "user_turns_count": len(payload.user_turns),
    }
    for f in extracted:
        predicate = f.predicate
        fact_source = source
        # R4 门控: 药物混杂指标 (转氨酶/尿酸/LDL/HbA1c/血压…) 上的因果有效性断言不可作为
        # 🟢 高可信记忆喂回 chat LLM —— 混杂的他汀/降尿酸药/降压药才可能是真因。降级为
        # 描述性 observed_change (保留观察, 不声称干预"有效/无效")。与 effect_estimator /
        # crossover_verdict 共用同一门控集 (intervention_priors), 不复制关键词。
        if predicate in _CAUSAL_EFFICACY_PREDICATES and gate_text_for_clinician(
            f"{f.subject} {f.object_value}"
        ):
            predicate = "observed_change"
            fact_source = {**source, "clinician_gated_demotion": f.predicate}
            demoted_count += 1
        fact = write_fact(
            db,
            user_id=current_user.id,
            tier="episodic",  # 对话来的事实先放 episodic, lifecycle task 会自动升 semantic
            subject=f.subject,
            predicate=predicate,
            object_value=f.object_value,
            object_unit=f.object_unit,
            confidence=f.confidence,
            source=fact_source,
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
        f"extracted={len(extracted)} written={len(written)} "
        f"clinician_demoted={demoted_count}"
    )
    return ExtractMemoryResponse(extracted_count=len(written), facts=written)
