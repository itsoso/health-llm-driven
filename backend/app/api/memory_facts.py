"""Memory Facts API — 个人知识库浏览/编辑接口."""
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.memory_fact import MemoryFact
from app.models.user import User
from app.services.memory_service import (
    write_fact, reinforce_fact, supersede_fact, get_active_facts,
    detect_contradictions, dismiss_fact,
)

router = APIRouter(prefix="/memory-facts", tags=["memory-facts"])


Tier = Literal["working", "episodic", "semantic", "procedural"]


class FactCreate(BaseModel):
    tier: Tier
    subject: str = Field(..., max_length=200)
    predicate: str = Field(..., max_length=80)
    object_value: str = Field(..., max_length=1000)
    object_unit: Optional[str] = Field(None, max_length=20)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    is_sensitive: bool = False


class FactReinforce(BaseModel):
    source_type: str = Field(..., max_length=40)
    source_id: Optional[str] = None
    weight: float = Field(0.5, ge=0.0, le=1.0)


def _to_dict(f: MemoryFact) -> dict:
    from app.services.memory_service import effective_memory_predicate

    return {
        "id": f.id,
        "tier": f.tier,
        "subject": f.subject,
        "predicate": effective_memory_predicate(
            f.predicate, object_value=f.object_value, tags=f.tags or [],
        ),
        "object_value": f.object_value,
        "object_unit": f.object_unit,
        "confidence": f.confidence,
        "effective_confidence": round(f.effective_confidence, 3),
        "reinforcement_count": f.reinforcement_count,
        "decay_rate": f.decay_rate,
        "sources": f.sources,
        "tags": f.tags,
        "is_sensitive": f.is_sensitive,
        "last_reinforced_at": f.last_reinforced_at.isoformat() if f.last_reinforced_at else None,
        "supersedes_id": f.supersedes_id,
        "superseded_by_id": f.superseded_by_id,
        "superseded_at": f.superseded_at.isoformat() if f.superseded_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.get("/me", summary="我的活跃事实 (按 effective_confidence 排)")
def list_mine(
    tier: Optional[Tier] = None,
    predicate: Optional[str] = None,
    tag: Optional[str] = None,
    subject_contains: Optional[str] = None,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    facts = get_active_facts(
        db, current_user.id,
        tier=tier, predicate=predicate, tag=tag,
        subject_contains=subject_contains, min_confidence=min_confidence,
        limit=limit,
    )
    # 按 effective_confidence 重排 (DB sort 用 last_reinforced_at, 这里 in-memory)
    facts.sort(key=lambda f: f.effective_confidence, reverse=True)
    return [_to_dict(f) for f in facts]


@router.post("", summary="手动创建事实")
def create_fact(
    body: FactCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    fact = write_fact(
        db, user_id=current_user.id,
        tier=body.tier, subject=body.subject,
        predicate=body.predicate, object_value=body.object_value,
        object_unit=body.object_unit, confidence=body.confidence,
        source={"type": "manual", "weight": 1.0},
        tags=body.tags, is_sensitive=body.is_sensitive,
    )
    if not fact:
        raise HTTPException(400, "fact 写入失败")
    return _to_dict(fact)


@router.post("/{fact_id}/reinforce", summary="增强事实 (新 source)")
def reinforce(
    fact_id: int,
    body: FactReinforce,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    fact = db.query(MemoryFact).filter(
        MemoryFact.id == fact_id,
        MemoryFact.user_id == current_user.id,
    ).first()
    if not fact:
        raise HTTPException(404, "fact 不存在")

    updated = reinforce_fact(
        db, fact_id,
        source={"type": body.source_type, "id": body.source_id, "weight": body.weight},
    )
    if not updated:
        raise HTTPException(500, "reinforce 失败")
    return _to_dict(updated)


@router.post("/{old_id}/supersede/{new_id}", summary="标记 old fact 被 new fact 替代")
def supersede(
    old_id: int, new_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # 鉴权: 双方都属于当前 user
    for fid in (old_id, new_id):
        f = db.query(MemoryFact).filter(
            MemoryFact.id == fid,
            MemoryFact.user_id == current_user.id,
        ).first()
        if not f:
            raise HTTPException(404, f"fact {fid} 不存在或不属于当前用户")
    if not supersede_fact(db, old_id, new_id):
        raise HTTPException(500, "supersede 失败")
    return {"old_id": old_id, "new_id": new_id, "ok": True}


@router.post("/{fact_id}/dismiss", summary="用户标记'这条不对' (soft-delete)")
def dismiss(
    fact_id: int,
    reason: str = Query("user_dismissed", max_length=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    fact = db.query(MemoryFact).filter(
        MemoryFact.id == fact_id,
        MemoryFact.user_id == current_user.id,
    ).first()
    if not fact:
        raise HTTPException(404, "fact 不存在或不属于当前用户")
    if fact.superseded_at is not None:
        raise HTTPException(409, "fact 已经归档")
    if not dismiss_fact(db, fact_id, reason=reason):
        raise HTTPException(500, "dismiss 失败")
    return {"id": fact_id, "dismissed": True, "reason": reason}


@router.get("/contradictions/check", summary="检测新事实与现有的矛盾")
def check_contradictions(
    subject: str = Query(..., max_length=200),
    predicate: str = Query(..., max_length=80),
    object_value: str = Query(..., max_length=1000),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    rows = detect_contradictions(
        db, current_user.id,
        subject=subject, predicate=predicate, object_value=object_value,
    )
    return {
        "count": len(rows),
        "contradicting_facts": [_to_dict(r) for r in rows],
    }


@router.get("/stats/me", summary="我的记忆统计")
def stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func
    rows = db.query(
        MemoryFact.tier,
        func.count(MemoryFact.id).label("total"),
        func.avg(MemoryFact.confidence).label("avg_conf"),
    ).filter(
        MemoryFact.user_id == current_user.id,
        MemoryFact.superseded_at.is_(None),
    ).group_by(MemoryFact.tier).all()

    return {
        "by_tier": [
            {"tier": r.tier, "total": int(r.total),
             "avg_confidence": round(float(r.avg_conf or 0), 3)}
            for r in rows
        ],
    }
