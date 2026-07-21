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
from app.services.system_knowledge_eval import run_system_kb_eval_cases
from app.services.system_knowledge_service import (
    adjudicate_dedao_kbase_review_claim,
    apply_dedao_kbase_review_verification_packet,
    approve_dedao_kbase_draft_review,
    generate_dedao_kbase_review_verification_packet,
    get_dedao_kbase_draft_review_bundle,
    get_claim_bundle,
    get_entity_bundle,
    get_knowledge_coverage_report,
    get_knowledge_operations_dashboard,
    get_knowledge_review_queue,
    lint_knowledge_base,
    list_dedao_kbase_review_claims,
    list_dedao_kbase_review_verification_packets,
    lookup_for_twin,
    preview_dedao_kbase_reviewed_artifacts_publish,
    publish_dedao_kbase_reviewed_artifacts,
    run_system_kb_reindex_report,
    search_knowledge,
    update_claim_review,
)

router = APIRouter(prefix="/knowledge", tags=["system-knowledge"])
# 治理隔离 belt-and-suspenders:admin_router 整个 router 级强制 get_admin_user。
# 每条路由仍各自声明 `Depends(get_admin_user)`(要 User 对象写审计),FastAPI 同请求内
# 缓存同一依赖只跑一次。router 级这道是为了将来新增路由**忘了**加 per-route 依赖时,
# 仍不会静默对任意登录用户开放(此 router 下有 /graph 等读未审 draft 的路径)。
admin_router = APIRouter(
    prefix="/admin/knowledge",
    tags=["admin-system-knowledge"],
    dependencies=[Depends(get_admin_user)],
)

# KBAudit.op is VARCHAR(40). Keep these explicit and schema-safe so a successful
# filesystem write cannot be reported as a 500 solely while recording metadata.
DEDAO_KBASE_VERIFICATION_GENERATED_OP = "dedao_kbase_verification_generated"
DEDAO_KBASE_VERIFICATION_APPLIED_OP = "dedao_kbase_verification_applied"
DedaoKbaseReviewWorkspace = Literal["release", "agent_package"]


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


class DedaoKbaseDraftReviewApproveRequest(BaseModel):
    workspace: DedaoKbaseReviewWorkspace = "release"
    workspace_fingerprint: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    note: str | None = Field(default=None, max_length=1000)
    publish: bool = False
    dry_run_publish: bool = False


class DedaoKbaseClaimEvidence(BaseModel):
    kind: str | None = Field(default=None, max_length=80)
    source: str = Field(..., min_length=1, max_length=300)
    title: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=1000)


class DedaoKbaseClaimAdjudicationRequest(BaseModel):
    workspace: DedaoKbaseReviewWorkspace = "release"
    workspace_fingerprint: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approve", "needs_evidence", "reject", "background_only"]
    note: str | None = Field(default=None, max_length=1000)
    evidence: DedaoKbaseClaimEvidence | None = None
    evidence_level: Literal["A", "B", "C", "D"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class DedaoKbaseVerificationPacketRequest(BaseModel):
    workspace: DedaoKbaseReviewWorkspace = "release"
    workspace_fingerprint: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class DedaoKbaseVerificationPacketApplyRequest(BaseModel):
    workspace: DedaoKbaseReviewWorkspace = "release"
    workspace_fingerprint: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    packet_id: str = Field(..., min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=1000)


class DedaoKbaseDraftReviewFinalizeRequest(BaseModel):
    workspace: DedaoKbaseReviewWorkspace = "release"
    workspace_fingerprint: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    note: str | None = Field(default=None, max_length=1000)


class DedaoKbasePublishPreviewRequest(BaseModel):
    workspace: DedaoKbaseReviewWorkspace = "release"
    note: str | None = Field(default=None, max_length=1000)


class DedaoKbaseReviewedArtifactsPublishRequest(BaseModel):
    workspace: DedaoKbaseReviewWorkspace = "release"
    note: str | None = Field(default=None, max_length=1000)


class ReconciliationDecisionRequest(BaseModel):
    action: Literal["approve_merge", "reject", "defer", "confirm_shadow"]
    note: str | None = Field(default=None, max_length=1000)


class ReconciliationAutoMergeRequest(BaseModel):
    # 空 = 什么都不自动(ships DISABLED);admin 显式传低危 entity_type 才对其 entity_align 自动合。
    enabled_entity_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=1000)


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
        diff={
            "q": result.get("query", ""),
            "limit": limit,
            "result_count": len(result["results"]),
            "input_guard": (result.get("retrieval_plan") or {}).get("input_guard") or {},
        },
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


@admin_router.get("/graph", summary="系统知识库邻域图(admin,种子+hops≤2;含 draft 节点)")
def get_system_knowledge_graph(
    seed: str = Query(..., description="种子文档 doc_id"),
    hops: int = Query(2, ge=1, le=2),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    # 治理隔离:此路径故意含 draft/needs_review 节点(reviewer 要看得见才审得动),
    # 只在 admin 读路径可达;Twin/Orchestrator 走 lookup_for_twin/search(reviewed 门)不受影响。
    from app.services.system_knowledge_graph import admin_expand_kb_neighborhood

    result = admin_expand_kb_neighborhood(db, seed, hops=hops)
    _record_audit(
        db,
        doc_id=seed,
        op="admin_graph_view",
        actor=f"admin:{admin_user.id}",
        diff={
            "nodes": result.get("node_count", 0),
            "hops": result.get("hops"),
            "truncated": result.get("truncated"),
        },
    )
    return result


@admin_router.get(
    "/document/{doc_id:path}",
    summary="系统知识库单文档全量(admin;provenance lineage 面板;含 draft/archived,不套 serving 门)",
)
def get_system_knowledge_document(
    doc_id: str,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    # 治理隔离:admin-only bypass 面(reviewer 看 provenance / P4 折入来源 / merged_into),
    # 与 /graph 同属;runtime serving(reviewed 门)不受影响。
    from app.services.system_knowledge_graph import admin_get_document

    doc = admin_get_document(db, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="知识库文档不存在")
    _record_audit(db, doc_id=doc_id, op="admin_document_view", actor=f"admin:{admin_user.id}")
    return doc


@admin_router.post(
    "/reconciliation/scan",
    summary="跨源对账 detector 扫描(Phase B P3;只写候选旁路表,零 serving mutation)",
)
def scan_reconciliation_candidates(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    # P3:确定性 detector 只读 kb_documents 找跨源重叠,只写 kb_reconciliation_candidate 旁路表。
    # 零 kb_documents/kb_edges mutation、零 auto-approve、零 merge(那些在 P4/P5,过 eval 才开)。
    from app.services.kb_reconciliation import detect_reconciliation_candidates

    result = detect_reconciliation_candidates(db, actor=f"admin:{admin_user.id}")
    _record_audit(
        db,
        doc_id=None,
        op="reconciliation_scan",
        actor=f"admin:{admin_user.id}",
        diff={
            "created": result.get("created"),
            "skipped_existing": result.get("skipped_existing"),
            "truncated": result.get("truncated"),
            "total_open": result.get("total_open"),
        },
    )
    return result


@admin_router.get(
    "/reconciliation/candidates",
    summary="跨源对账候选队列(Phase B P3;只读)",
)
def get_reconciliation_candidates(
    status: str | None = Query("open", description="open|approved|rejected|deferred"),
    kind: str | None = Query(None, description="entity_align|claim_overlap"),
    relation_tag: str | None = Query(None, description="duplicate|agree|conflict|complementary"),
    shadow_pending: bool = Query(False, description="只看待影子复核的 auto 合(强制 status=approved)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if shadow_pending:
        # 全量 approved 过滤后分页(页内过滤会埋 pending + total 虚报 = 人环 fail-open)
        from app.services.kb_reconciliation import list_shadow_pending

        return list_shadow_pending(db, limit=limit, offset=offset)

    from app.services.kb_reconciliation import list_reconciliation_candidates

    return list_reconciliation_candidates(
        db,
        status=status,
        kind=kind,
        relation_tag=relation_tag,
        limit=limit,
        offset=offset,
    )


@admin_router.get(
    "/reconciliation/breaker",
    summary="auto 熔断状态(P6;**粘性**:reset 后任一检出误合即熔断,直到显式人工 reset)",
)
def get_reconciliation_breaker(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from app.services.kb_reconciliation_judge import auto_breaker_status

    return auto_breaker_status(db)


class BreakerResetRequest(BaseModel):
    note: str = Field(..., min_length=5, max_length=500, description="必填:说明误合已如何复核处理")


@admin_router.post(
    "/reconciliation/breaker/reset",
    summary="人工复位熔断(P6;审计化,确认 reset 前误合已复核;新误合会再次熔断)",
)
def post_reconciliation_breaker_reset(
    body: BreakerResetRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from app.services.kb_reconciliation_judge import reset_auto_breaker

    return reset_auto_breaker(db, actor=f"admin:{admin_user.id}", note=body.note)


@admin_router.patch(
    "/reconciliation/candidates/{candidate_id}",
    summary="对账候选裁决(Phase B P4;approve_merge=首个 serving mutation / reject / defer)",
)
def review_reconciliation_candidate(
    candidate_id: int,
    body: "ReconciliationDecisionRequest",
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from app.models.system_knowledge import KBReconciliationCandidate

    actor = f"admin:{admin_user.id}"
    if body.action == "approve_merge":
        # 人工 approve → 合并(conflict/prescriptive/无锚 → 硬拒 400,fail-loud)
        from app.services.kb_reconciliation_merge import merge_candidate

        try:
            return merge_candidate(db, candidate_id, actor=actor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    cand = (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.id == candidate_id)
        .first()
    )
    if cand is None:
        raise HTTPException(status_code=404, detail="candidate 不存在")

    if body.action == "confirm_shadow":
        # 影子复核确认:人看过这笔 auto 合,判定正确(判定错误 → 走 unalign,那才是误合信号)
        from app.services.kb_reconciliation_judge import confirm_shadow_audit

        try:
            return confirm_shadow_audit(db, candidate_id, actor=actor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # reject / defer:仅改 status,不动 serving
    if cand.status != "open":
        raise HTTPException(status_code=400, detail=f"candidate status={cand.status},非 open 不可裁决")
    cand.status = "rejected" if body.action == "reject" else "deferred"
    cand.reviewed_by = actor
    _record_audit(db, doc_id=None, op=f"reconciliation_{body.action}", actor=actor,
                  diff={"candidate_id": candidate_id})
    return {"candidate_id": candidate_id, "status": cand.status}


@admin_router.post(
    "/reconciliation/candidates/{candidate_id}/unalign",
    summary="撤销一次 merge(Phase B P4;字节还原,可逆性是 P5 auto 的前置)",
)
def unalign_reconciliation_candidate(
    candidate_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from app.services.kb_reconciliation_merge import unalign_candidate

    try:
        return unalign_candidate(db, candidate_id, actor=f"admin:{admin_user.id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@admin_router.post(
    "/reconciliation/judge",
    summary="对 open 候选跑 LLM judge(Phase B P5;advisory,写 relation_tag/score,不自动合)",
)
def run_reconciliation_judge(
    limit: int = Query(200, ge=1, le=1000),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    # judge-only:enabled_entity_types 空 → 只分类不自动合并
    from app.services.kb_reconciliation_judge import run_judge_and_auto

    result = run_judge_and_auto(db, actor=f"admin:{admin_user.id}", enabled_entity_types=frozenset(), limit=limit)
    _record_audit(db, doc_id=None, op="reconciliation_judge", actor=f"admin:{admin_user.id}",
                  diff={"judged": result["judged"]})
    return result


@admin_router.post(
    "/reconciliation/auto_merge",
    summary=("P5 无人自动合(**默认 DISABLED**:只对显式 enabled_entity_types 的 entity_align 跑)。"
             "⚠️ 运营纪律:P6 影子审计 + 速率熔断上线前,enabled_entity_types **必须留空**"
             "(§10:τ=0.95 会放过部分近似,无运行时后备不得开任何 type 的 auto)。"),
)
def run_reconciliation_auto_merge(
    body: "ReconciliationAutoMergeRequest",
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    # 显式传入 enabled_entity_types 才自动;空集 = 什么都不自动(ships DISABLED)。
    from app.services.kb_reconciliation_judge import run_judge_and_auto

    result = run_judge_and_auto(
        db,
        actor=f"admin:{admin_user.id}",
        enabled_entity_types=frozenset(body.enabled_entity_types or ()),
        limit=body.limit,
    )
    _record_audit(db, doc_id=None, op="reconciliation_auto_merge", actor=f"admin:{admin_user.id}",
                  diff={"auto_merged": result["auto_merged"], "enabled": result["enabled_entity_types"]})
    return result


@admin_router.post(
    "/reconciliation/auto_merge/preview",
    summary=("Dry-run:跑真 judge + 9 闸,报「会 auto 合的候选」+ 各 skip 理由,**零 serving mutation**。"
             "首次为某 entity_type 开 auto 前先 preview 眼看这批(含真实分数)再翻 enable。"),
)
def preview_reconciliation_auto_merge(
    body: "ReconciliationAutoMergeRequest",
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from app.services.kb_reconciliation_judge import preview_auto_merge

    result = preview_auto_merge(
        db,
        enabled_entity_types=frozenset(body.enabled_entity_types or ()),
        limit=body.limit,
    )
    _record_audit(db, doc_id=None, op="reconciliation_auto_merge_preview", actor=f"admin:{admin_user.id}",
                  diff={"would_auto_merge_count": result["would_auto_merge_count"],
                        "enabled": result["enabled_entity_types"]})
    return result


@admin_router.post(
    "/reconciliation/eval",
    summary="P5 判重/auto eval(Phase B;测 precision + auto FP,不改 serving)",
)
def run_reconciliation_eval(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from app.services.kb_reconciliation_eval import run_dedup_judge_eval

    result = run_dedup_judge_eval(db)
    _record_audit(db, doc_id=None, op="reconciliation_eval", actor=f"admin:{admin_user.id}",
                  diff={"n": result["n"], "auto_approve_fp": result["auto_approve_fp"]})
    return result


@admin_router.get("/eval_report", summary="系统知识库 eval case 运行报告")
def get_system_knowledge_eval_report(
    case_id: list[str] | None = Query(None),
    limit: int = Query(50, ge=1, le=10000),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    result = run_system_kb_eval_cases(db, case_ids=case_id or None, limit=limit)
    _record_audit(
        db,
        doc_id=None,
        op="eval_report",
        actor=f"admin:{admin_user.id}",
        diff={
            "total": result["total"],
            "passed": result["passed"],
            "failed": result["failed"],
            "case_id_count": len(case_id or []),
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


@admin_router.get("/dedao_kbase/draft_review", summary="查看 dedao-kbase draft artifact review 包")
def get_dedao_kbase_draft_review(
    workspace: DedaoKbaseReviewWorkspace = Query(default="release"),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        result = get_dedao_kbase_draft_review_bundle(workspace=workspace)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _record_audit(
        db,
        doc_id=None,
        op="dedao_kbase_draft_review_bundle",
        actor=f"admin:{admin_user.id}",
        diff={
            "artifact_dir": result["artifact_dir"],
            "serving_allowed": result["gate"]["serving_allowed"],
            "blocking_reasons": result["gate"]["blocking_reasons"],
            "preview_counts": result["preview"]["counts"],
            "workspace": workspace,
        },
    )
    return result


@admin_router.get("/dedao_kbase/draft_review/items", summary="分页查看 dedao-kbase draft claims")
def get_dedao_kbase_draft_review_items(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    decision: Literal["approve", "needs_evidence", "reject", "background_only"] | None = Query(default=None),
    workspace: DedaoKbaseReviewWorkspace = Query(default="release"),
    admin_user: User = Depends(get_admin_user),
):
    try:
        return list_dedao_kbase_review_claims(
            offset=offset, limit=limit, decision=decision, workspace=workspace
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.get(
    "/dedao_kbase/draft_review/items/{doc_id}/verification",
    summary="查看 dedao-kbase claim verification packets",
)
def get_dedao_kbase_verification_packets(
    doc_id: str,
    workspace: DedaoKbaseReviewWorkspace = Query(default="release"),
    admin_user: User = Depends(get_admin_user),
):
    try:
        return list_dedao_kbase_review_verification_packets(
            doc_id=doc_id, workspace=workspace
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.post(
    "/dedao_kbase/draft_review/items/{doc_id}/verification",
    summary="生成 dedao-kbase claim verification packet",
)
def generate_dedao_kbase_verification_packet(
    doc_id: str,
    request: DedaoKbaseVerificationPacketRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        result = generate_dedao_kbase_review_verification_packet(
            doc_id=doc_id,
            expected_workspace_fingerprint=request.workspace_fingerprint,
            workspace=request.workspace,
        )
    except (OSError, ValueError) as exc:
        status_code = 409 if "changed since preview" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    packet = result["packet"]
    _record_audit(
        db,
        doc_id=doc_id,
        op=DEDAO_KBASE_VERIFICATION_GENERATED_OP,
        actor=f"admin:{admin_user.id}",
        diff={
            "packet_id": packet["packet_id"],
            "status": packet["status"],
            "proposed_decision": packet["proposed_decision"],
            "workspace_fingerprint": result["workspace_fingerprint"],
            "check_statuses": {
                item["code"]: item["status"]
                for item in packet.get("checks") or []
            },
            "citation_ids": packet.get("citation_ids") or [],
            "generator": packet.get("generator"),
            "workspace": request.workspace,
        },
    )
    return result


@admin_router.post(
    "/dedao_kbase/draft_review/items/{doc_id}/verification/apply",
    summary="采纳 dedao-kbase claim verification packet 建议",
)
def apply_dedao_kbase_verification_packet(
    doc_id: str,
    request: DedaoKbaseVerificationPacketApplyRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        result = apply_dedao_kbase_review_verification_packet(
            doc_id=doc_id,
            packet_id=request.packet_id,
            reviewer=f"admin:{admin_user.id}",
            expected_workspace_fingerprint=request.workspace_fingerprint,
            note=request.note,
            workspace=request.workspace,
        )
    except (OSError, ValueError) as exc:
        message = str(exc)
        status_code = 409 if "changed since preview" in message or "is stale" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    _record_audit(
        db,
        doc_id=doc_id,
        op=DEDAO_KBASE_VERIFICATION_APPLIED_OP,
        actor=f"admin:{admin_user.id}",
        diff={
            "packet_id": request.packet_id,
            "decision": result["decision"],
            "release_id": result.get("release_id"),
            "release_claim_id": result.get("release_claim_id"),
            "note": request.note,
            "workspace_fingerprint": result["workspace_fingerprint"],
            "workspace": request.workspace,
        },
    )
    return result


@admin_router.patch("/dedao_kbase/draft_review/items/{doc_id}", summary="裁决一个 dedao-kbase draft claim")
def adjudicate_dedao_kbase_draft_review_item(
    doc_id: str,
    request: DedaoKbaseClaimAdjudicationRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    evidence = request.evidence.model_dump(exclude_none=True) if request.evidence else None
    try:
        result = adjudicate_dedao_kbase_review_claim(
            doc_id=doc_id,
            decision=request.decision,
            reviewer=f"admin:{admin_user.id}",
            expected_workspace_fingerprint=request.workspace_fingerprint,
            note=request.note,
            evidence=evidence,
            evidence_level=request.evidence_level,
            confidence=request.confidence,
            workspace=request.workspace,
        )
    except (OSError, ValueError) as exc:
        status_code = 409 if "changed since preview" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    _record_audit(
        db,
        doc_id=doc_id,
        op="dedao_kbase_claim_adjudicated",
        actor=f"admin:{admin_user.id}",
        diff={
            "decision": request.decision,
            "release_id": result.get("release_id"),
            "release_claim_id": result.get("release_claim_id"),
            "note": request.note,
            "evidence": evidence,
            "evidence_level": request.evidence_level,
            "confidence": request.confidence,
            "workspace_fingerprint": result["workspace_fingerprint"],
            "workspace": request.workspace,
        },
    )
    return result


@admin_router.post("/dedao_kbase/draft_review/finalize", summary="最终确认已逐条裁决的 dedao-kbase review")
def finalize_dedao_kbase_draft_review_endpoint(
    request: DedaoKbaseDraftReviewFinalizeRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        result = approve_dedao_kbase_draft_review(
            reviewer=f"admin:{admin_user.id}",
            expected_workspace_fingerprint=request.workspace_fingerprint,
            workspace=request.workspace,
        )
    except (OSError, ValueError) as exc:
        status_code = 409 if "changed since preview" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    _record_audit(
        db,
        doc_id=None,
        op="dedao_kbase_draft_review_finalized",
        actor=f"admin:{admin_user.id}",
        diff={
            "note": request.note,
            "serving_allowed": result["gate"]["serving_allowed"],
            "blocking_reasons": result["gate"]["blocking_reasons"],
            "workspace_fingerprint": result["workspace_fingerprint"],
            "workspace": request.workspace,
        },
    )
    return result


@admin_router.post("/dedao_kbase/draft_review/approve", summary="批准 dedao-kbase draft artifacts")
def approve_dedao_kbase_draft_review_endpoint(
    request: DedaoKbaseDraftReviewApproveRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        if request.publish or request.dry_run_publish:
            raise ValueError(
                "legacy draft approval no longer supports publish; finalize review and use the separate preview endpoint"
            )
        result = approve_dedao_kbase_draft_review(
            reviewer=f"admin:{admin_user.id}",
            expected_workspace_fingerprint=request.workspace_fingerprint,
            workspace=request.workspace,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _record_audit(
        db,
        doc_id=None,
        op="dedao_kbase_draft_review_approved",
        actor=f"admin:{admin_user.id}",
        diff={
            "artifact_dir": result["artifact_dir"],
            "serving_allowed": result["gate"]["serving_allowed"],
            "blocking_reasons": result["gate"]["blocking_reasons"],
            "reviewed_at": result["review"].get("reviewed_at"),
            "documents_reviewed": result["review"].get("documents_reviewed"),
            "relations_reviewed": result["review"].get("relations_reviewed"),
            "note": request.note,
            "published": False,
            "publish_dry_run": False,
            "workspace": request.workspace,
        },
    )
    return result


@admin_router.post(
    "/dedao_kbase/reviewed_artifacts/publish/preview",
    summary="预演发布已审核 dedao-kbase artifacts",
)
def preview_dedao_kbase_reviewed_artifacts_publish_endpoint(
    request: DedaoKbasePublishPreviewRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        result = preview_dedao_kbase_reviewed_artifacts_publish(
            db, workspace=request.workspace
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_audit(
        db,
        doc_id=None,
        op="dedao_kbase_reviewed_artifacts_publish_preview",
        actor=f"admin:{admin_user.id}",
        diff={
            "note": request.note,
            "dry_run": True,
            "import": result["import"],
            "reindex": result["reindex"],
            "workspace": request.workspace,
        },
    )
    return result


@admin_router.post("/dedao_kbase/reviewed_artifacts/publish", summary="发布已审核 dedao-kbase artifacts")
def publish_dedao_kbase_reviewed_artifacts_endpoint(
    request: DedaoKbaseReviewedArtifactsPublishRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        result = publish_dedao_kbase_reviewed_artifacts(
            db,
            actor=f"admin:{admin_user.id}",
            workspace=request.workspace,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _record_audit(
        db,
        doc_id=None,
        op="dedao_kbase_reviewed_artifacts_published",
        actor=f"admin:{admin_user.id}",
        diff={
            "artifact_dir": result["artifact_dir"],
            "published": True,
            "note": request.note,
            "import": result["import"],
            "reindex": result["reindex"],
            "workspace": request.workspace,
        },
    )
    return result


@admin_router.post("/reindex", summary="重建系统知识库检索字段")
def reindex_system_knowledge(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return run_system_kb_reindex_report(db, actor=f"admin:{admin_user.id}")


def _record_audit(
    db: Session,
    doc_id: str | None,
    op: str,
    actor: str,
    diff: dict[str, Any] | None = None,
) -> None:
    db.add(KBAudit(doc_id=doc_id, op=op, actor=actor, diff=diff or {}))
    db.commit()
