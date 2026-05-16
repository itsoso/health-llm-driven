"""System knowledge API backed by the LLM Wiki v2 compiled store."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.system_knowledge import KBAudit
from app.models.user import User
from app.services.system_knowledge_service import get_entity_bundle, lookup_for_twin

router = APIRouter(prefix="/knowledge", tags=["system-knowledge"])


class TwinLookupRequest(BaseModel):
    genetics: dict[str, Any] = Field(default_factory=dict)
    labs: dict[str, Any] = Field(default_factory=dict)
    wearable: dict[str, Any] = Field(default_factory=dict)
    medications: list[dict[str, Any]] = Field(default_factory=list)
    supplements: list[dict[str, Any]] = Field(default_factory=list)
    goals: dict[str, Any] = Field(default_factory=dict)


@router.get("/entity/{entity_type}/{entity_id}", summary="获取系统知识库实体与关联 claim")
def get_knowledge_entity(
    entity_type: str,
    entity_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    bundle = get_entity_bundle(db, entity_type=entity_type, entity_id=entity_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="知识库实体不存在")

    _record_audit(db, doc_id=bundle["entity"]["doc_id"], op="query_entity", actor=f"user:{current_user.id}")
    return bundle


@router.post("/lookup_for_twin", summary="基于 Twin 摘要查找系统知识库条目")
def lookup_knowledge_for_twin(
    request: TwinLookupRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    payload = request.model_dump()
    result = lookup_for_twin(db, payload)
    _record_audit(
        db,
        doc_id=None,
        op="lookup_for_twin",
        actor=f"user:{current_user.id}",
        diff={
            "entity_count": len(result["entities"]),
            "claim_count": len(result["claims"]),
        },
    )
    return result


def _record_audit(
    db: Session,
    doc_id: str | None,
    op: str,
    actor: str,
    diff: dict[str, Any] | None = None,
) -> None:
    db.add(KBAudit(doc_id=doc_id, op=op, actor=actor, diff=diff or {}))
    db.commit()
