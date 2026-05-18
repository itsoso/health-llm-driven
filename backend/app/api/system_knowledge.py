"""System knowledge API backed by the LLM Wiki v2 compiled store."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.system_knowledge import KBAudit
from app.models.user import User
from app.services.system_knowledge_service import (
    get_claim_bundle,
    get_entity_bundle,
    get_knowledge_coverage_report,
    get_knowledge_operations_dashboard,
    get_knowledge_review_queue,
    lint_knowledge_base,
    lookup_for_twin,
    reindex_knowledge_documents,
    search_knowledge,
    update_claim_review,
)

router = APIRouter(prefix="/knowledge", tags=["system-knowledge"])
admin_router = APIRouter(prefix="/admin/knowledge", tags=["admin-system-knowledge"])


class TwinLookupRequest(BaseModel):
    genetics: dict[str, Any] = Field(default_factory=dict)
    labs: dict[str, Any] = Field(default_factory=dict)
    wearable: dict[str, Any] = Field(default_factory=dict)
    medications: list[dict[str, Any]] = Field(default_factory=list)
    supplements: list[dict[str, Any]] = Field(default_factory=list)
    goals: dict[str, Any] = Field(default_factory=dict)


class ClaimFeedbackRequest(BaseModel):
    feedback: Literal["disagree"] = "disagree"
    reason: str | None = Field(default=None, max_length=500)


class ExternalSourceReviewRequest(BaseModel):
    kind: str | None = Field(default=None, max_length=80)
    source: str = Field(..., min_length=1, max_length=300)
    title: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=1000)
    review_status: Literal["reviewed", "needs_review", "draft"] = "reviewed"


class ClaimReviewUpdateRequest(BaseModel):
    review_status: Literal["draft", "reviewed", "needs_review", "archived"] | None = None
    evidence_level: Literal["A", "B", "C", "D"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    external_source: ExternalSourceReviewRequest | None = None
    clear_candidate_duplicates: bool = False
    resolve_feedback: bool = False
    note: str | None = Field(default=None, max_length=1000)


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


@router.get("/claim/{claim_id}", summary="获取系统知识库 claim 详情")
def get_knowledge_claim(
    claim_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    bundle = get_claim_bundle(db, claim_id=claim_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="知识库 claim 不存在")

    _record_audit(db, doc_id=bundle["claim"]["doc_id"], op="query_claim", actor=f"user:{current_user.id}")
    return bundle


@router.post("/claim/{claim_id}/feedback", summary="反馈系统知识库 claim 不适用或不准确")
def submit_knowledge_claim_feedback(
    claim_id: str,
    request: ClaimFeedbackRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    bundle = get_claim_bundle(db, claim_id=claim_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="知识库 claim 不存在")

    op = "feedback_disagree" if request.feedback == "disagree" else f"feedback_{request.feedback}"
    _record_audit(
        db,
        doc_id=bundle["claim"]["doc_id"],
        op=op,
        actor=f"user:{current_user.id}",
        diff={
            "feedback": request.feedback,
            "reason": request.reason,
            "claim_title": bundle["claim"].get("title"),
        },
    )
    return {"ok": True, "claim_id": bundle["claim"]["doc_id"], "op": op}


@router.get("/search", summary="搜索系统知识库")
def search_system_knowledge(
    q: str = Query("", max_length=200),
    limit: int = Query(10, ge=1, le=50),
    doc_type: str | None = Query(None),
    entity_type: str | None = Query(None),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    result = search_knowledge(
        db,
        q,
        limit=limit,
        doc_type=doc_type,
        entity_type=entity_type,
    )
    _record_audit(
        db,
        doc_id=None,
        op="search",
        actor=f"user:{current_user.id}",
        diff={"q": q, "limit": limit, "result_count": len(result["results"])},
    )
    return result


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


@admin_router.get("/lint_report", summary="系统知识库 lint 报告")
def get_system_knowledge_lint_report(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    result = lint_knowledge_base(db)
    _record_audit(
        db,
        doc_id=None,
        op="lint_report",
        actor=f"admin:{admin_user.id}",
        diff={"summary": result["summary"]},
    )
    return result


@admin_router.get("/coverage_report", summary="系统知识库覆盖率与 unsupported 看板")
def get_system_knowledge_coverage_report(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    result = get_knowledge_coverage_report(db)
    _record_audit(
        db,
        doc_id=None,
        op="coverage_report",
        actor=f"admin:{admin_user.id}",
        diff={
            "documents": result["documents"]["total"],
            "specialist_findings": result["specialist_findings"]["total"],
            "unsupported": result["specialist_findings"]["unsupported"],
        },
    )
    return result


@admin_router.get("/review_queue", summary="系统知识库人工 review 队列")
def get_system_knowledge_review_queue(
    limit: int = Query(100, ge=1, le=500),
    reason: str | None = Query(None, max_length=80),
    review_status: str | None = Query(None, max_length=40),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    result = get_knowledge_review_queue(
        db,
        limit=limit,
        reason=reason,
        review_status=review_status,
    )
    _record_audit(
        db,
        doc_id=None,
        op="review_queue",
        actor=f"admin:{admin_user.id}",
        diff={
            "total": result["summary"]["total"],
            "returned": result["summary"]["returned"],
            "reason": reason,
            "review_status": review_status,
        },
    )
    return result


@admin_router.patch("/claim/{claim_id}/review", summary="更新系统知识库 claim review 状态")
def update_system_knowledge_claim_review(
    claim_id: str,
    request: ClaimReviewUpdateRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        result = update_claim_review(
            db,
            claim_id,
            actor=f"admin:{admin_user.id}",
            review_status=request.review_status,
            evidence_level=request.evidence_level,
            confidence=request.confidence,
            external_source=request.external_source.model_dump() if request.external_source else None,
            clear_candidate_duplicates=request.clear_candidate_duplicates,
            resolve_feedback=request.resolve_feedback,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(status_code=404, detail="知识库 claim 不存在")
    return result


@admin_router.get("/operations_dashboard", summary="系统知识库运营治理总览")
def get_system_knowledge_operations_dashboard(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    result = get_knowledge_operations_dashboard(db)
    _record_audit(
        db,
        doc_id=None,
        op="operations_dashboard",
        actor=f"admin:{admin_user.id}",
        diff={
            "status": result["status"],
            "action_items": result["action_items"],
            "documents": result["coverage"]["documents"]["total"],
        },
    )
    return result


@admin_router.post("/reindex", summary="重建系统知识库检索字段")
def reindex_system_knowledge(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return reindex_knowledge_documents(db, actor=f"admin:{admin_user.id}")


def _record_audit(
    db: Session,
    doc_id: str | None,
    op: str,
    actor: str,
    diff: dict[str, Any] | None = None,
) -> None:
    db.add(KBAudit(doc_id=doc_id, op=op, actor=actor, diff=diff or {}))
    db.commit()
