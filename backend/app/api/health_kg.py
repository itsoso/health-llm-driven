"""Health Knowledge Graph API."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.health_kg import HealthEntity, EntityRelation
from app.models.user import User
from app.services.kg_service import (
    upsert_entity, match_entity, create_relation, get_relations,
    expand_neighborhood, mention_to_entities,
)

router = APIRouter(prefix="/health-kg", tags=["health-kg"])


class EntityCreate(BaseModel):
    type: str = Field(..., max_length=40)
    canonical_name: str = Field(..., max_length=200)
    aliases: List[str] = Field(default_factory=list)
    attributes: dict = Field(default_factory=dict)
    confidence: float = Field(0.7, ge=0.0, le=1.0)


class RelationCreate(BaseModel):
    subject_id: int
    predicate: str = Field(..., max_length=40)
    object_id: int
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    notes: Optional[str] = None


def _ent_dict(e: HealthEntity) -> dict:
    return {
        "id": e.id,
        "type": e.type,
        "canonical_name": e.canonical_name,
        "aliases": e.aliases,
        "attributes": e.attributes,
        "confidence": e.confidence,
        "is_active": e.is_active,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _rel_dict(r: EntityRelation) -> dict:
    return {
        "id": r.id,
        "subject_id": r.subject_id,
        "predicate": r.predicate,
        "object_id": r.object_id,
        "confidence": r.confidence,
        "evidence_count": r.evidence_count,
        "is_active": r.is_active,
        "notes": r.notes,
    }


@router.get("/entities/me", summary="我的所有 active entities")
def list_entities(
    type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    q = db.query(HealthEntity).filter(
        HealthEntity.user_id == current_user.id,
        HealthEntity.is_active == True,  # noqa: E712
    )
    if type:
        q = q.filter(HealthEntity.type == type)
    rows = q.order_by(HealthEntity.confidence.desc()).limit(limit).all()
    return [_ent_dict(r) for r in rows]


@router.post("/entities", summary="手动创建 entity")
def create_entity(
    body: EntityCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    ent = upsert_entity(
        db, user_id=current_user.id,
        type=body.type, canonical_name=body.canonical_name,
        aliases=body.aliases, attributes=body.attributes,
        confidence=body.confidence,
        source={"type": "manual"},
    )
    if not ent:
        raise HTTPException(400, "entity 写入失败 — 检查 type 是否合法")
    return _ent_dict(ent)


@router.get("/entities/{entity_id}", summary="entity 详情")
def get_entity(
    entity_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    ent = db.query(HealthEntity).filter(
        HealthEntity.id == entity_id,
        HealthEntity.user_id == current_user.id,
    ).first()
    if not ent:
        raise HTTPException(404, "entity 不存在")
    return _ent_dict(ent)


@router.get("/entities/{entity_id}/neighborhood", summary="entity 2-hop 邻域")
def neighborhood(
    entity_id: int,
    hops: int = Query(2, ge=1, le=3),
    max_per_hop: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    nbrs = expand_neighborhood(db, current_user.id, entity_id,
                               hops=hops, max_per_hop=max_per_hop)
    return {"entity_id": entity_id, "neighbors": nbrs}


@router.get("/match", summary="文字 → 匹配的 entity (canonical/alias)")
def match(
    mention: str = Query(..., max_length=200),
    type: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    ent = match_entity(db, current_user.id, mention, type=type)
    return {"matched": _ent_dict(ent) if ent else None}


@router.post("/relations", summary="手动创建 relation")
def create_rel(
    body: RelationCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # 鉴权: subject + object 都属于该 user
    for eid in (body.subject_id, body.object_id):
        e = db.query(HealthEntity).filter(
            HealthEntity.id == eid,
            HealthEntity.user_id == current_user.id,
        ).first()
        if not e:
            raise HTTPException(404, f"entity {eid} 不存在或不属于当前用户")

    rel = create_relation(
        db, user_id=current_user.id,
        subject_id=body.subject_id, predicate=body.predicate,
        object_id=body.object_id, confidence=body.confidence,
        notes=body.notes, source={"type": "manual"},
    )
    if not rel:
        raise HTTPException(400, "relation 写入失败 — 检查 predicate / 自环")
    return _rel_dict(rel)


@router.get("/relations/me", summary="我的所有 relations")
def list_relations(
    subject_id: Optional[int] = None,
    object_id: Optional[int] = None,
    predicate: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    rows = get_relations(
        db, user_id=current_user.id,
        subject_id=subject_id, object_id=object_id,
        predicate=predicate, limit=limit,
    )
    return [_rel_dict(r) for r in rows]


@router.get("/extract", summary="从一段文字抽 mentioned entities")
def extract(
    text: str = Query(..., max_length=2000),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    ents = mention_to_entities(db, current_user.id, text)
    return [_ent_dict(e) for e in ents]
