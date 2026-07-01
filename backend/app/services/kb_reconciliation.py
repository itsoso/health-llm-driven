"""System KB V2 跨源对账 —— Phase B P3(确定性 detector + 只读队列)。

**范围(P3 严格边界,越界=bug)**:
- **只读 serving 数据**:读 kb_documents(非归档)找跨源重叠;**零** kb_documents/kb_edges mutation。
- **只写旁路表** kb_reconciliation_candidate(合并前可审状态)。
- **零 auto-approve、零 merge**:那是 P4(人工 merge + unalign)/ P5(judge + can_auto_approve,
  过逐 entity_type 零误合 eval 才开)的活。本模块**没有** can_auto_approve / merge 函数。
- `resolve_canonical` 是**纯函数**(D1:down-dedao reviewed 恒 canonical),只产 `canonical_hint`
  给 reviewer 看,**不 mutate 任何东西**。

**治理隔离**:本表是 authoring/审核面对象,健康运行时(lookup_for_twin / knowledge_librarian /
search_knowledge)只读 kb_documents 且套 reviewed 门,**永不读本表** —— 候选永不进 Twin/Orchestrator。

确定性 detector 只做**结构性**跨源重叠(同 content_hash / 同 entity_id / 归一 title 相同),
只在 content_hash 完全相同(字节同内容)时敢标 relation_tag='duplicate';弱信号留 NULL 待 P5 judge。
语义判定(agree/conflict/complementary)与处方地板一律不在 P3。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument, KBReconciliationCandidate
from app.services.system_knowledge_service import _normalize_knowledge_text

DOWN_DEDAO_ORIGIN = "down-dedao-llm-wiki"
UNKNOWN = "unknown"
_ENTITY_DOC_TYPE = "entity"

# 确定性信号权重(纯结构,informational;P5 judge 才定 τ)。
_SIGNAL_WEIGHTS = {"content_hash": 0.7, "entity_id": 0.5, "normalized_title": 0.4}
_EVIDENCE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}
# 防跑飞:单次扫描最多写这么多候选(863 doc/15 类型下远够;KB 长大后截断而非静默全扫)。
_MAX_CANDIDATES_PER_SCAN = 5000
# 桶级 O(n²) 上界:单个 content_hash/entity_id/title 桶超过这么多文档就**不逐对展开**
# (真跨源重复簇只有几篇;100+ 篇同 hash/同 id 是数据病态 = 批量重复,须 reviewer 整簇看,
# 不是 ~5000 条两两候选)。跳过的桶数在返回 + 审计里 fail-loud 暴露,不静默全扫爆内存。
_MAX_BUCKET_SIZE = 100


def _origin(doc: KBDocument) -> str:
    return str((doc.metadata_json or {}).get("origin") or UNKNOWN)


def _review_status(doc: KBDocument) -> str:
    return str((doc.metadata_json or {}).get("review_status") or "")


def _is_reviewed_downdedao(doc: KBDocument) -> bool:
    return (
        _origin(doc) == DOWN_DEDAO_ORIGIN
        and _review_status(doc) == "reviewed"
        and not doc.is_archived
    )


def _tiebreak_same_class(a: KBDocument, b: KBDocument) -> str:
    """两侧都 reviewed down-dedao 时的确定性 hint(evidence_level → doc_id 升序)。

    注意:edge-degree 维度须查 DB,留到 P4/P5 approve 时事务内重算;P3 hint 只到 evidence+doc_id。
    """
    ra = _EVIDENCE_RANK.get((a.evidence_level or "").upper(), 0)
    rb = _EVIDENCE_RANK.get((b.evidence_level or "").upper(), 0)
    if ra != rb:
        return a.doc_id if ra > rb else b.doc_id
    return min(a.doc_id, b.doc_id)


def resolve_canonical(left: KBDocument, right: KBDocument) -> Tuple[Optional[str], str]:
    """D1 纯函数:down-dedao reviewed 恒为 canonical。返回 (canonical_doc_id | None, reason)。

    None = 无 reviewed down-dedao 锚(两个 draft,或 down-dedao 未 reviewed)→ 只能走人,
    P5 auto-approve 对这种硬拒(422)。**本函数零副作用、不碰 DB。**
    """
    lrd = _is_reviewed_downdedao(left)
    rrd = _is_reviewed_downdedao(right)
    if lrd and not rrd:
        return left.doc_id, "down-dedao reviewed anchor"
    if rrd and not lrd:
        return right.doc_id, "down-dedao reviewed anchor"
    if lrd and rrd:
        return _tiebreak_same_class(left, right), "same-class reviewed (v1 auto disabled)"
    return None, "no reviewed down-dedao anchor -> human"


def _kind_for(a: KBDocument, b: KBDocument) -> Optional[str]:
    """entity_align(两侧都 entity)/ claim_overlap(两侧都非 entity)/ None(混合,不成对)。"""
    a_ent = a.doc_type == _ENTITY_DOC_TYPE
    b_ent = b.doc_type == _ENTITY_DOC_TYPE
    if a_ent and b_ent:
        return "entity_align"
    if not a_ent and not b_ent:
        return "claim_overlap"
    return None  # entity × claim 不是合并候选


def _norm_title(title: Any) -> str:
    return _normalize_knowledge_text(title or "")


def _build_buckets(
    docs: List[KBDocument],
) -> Tuple[Dict[str, List[KBDocument]], Dict[str, List[KBDocument]], Dict[Tuple[str, str], List[KBDocument]]]:
    by_hash: Dict[str, List[KBDocument]] = {}
    by_entity: Dict[str, List[KBDocument]] = {}
    by_title: Dict[Tuple[str, str], List[KBDocument]] = {}
    for d in docs:
        if d.content_hash:
            by_hash.setdefault(d.content_hash, []).append(d)
        if d.entity_id:
            by_entity.setdefault(d.entity_id, []).append(d)
        tkey = _norm_title(d.title)
        if tkey:
            by_title.setdefault((str(d.entity_type or UNKNOWN), tkey), []).append(d)
    return by_hash, by_entity, by_title


def _cross_origin_pairs(group: List[KBDocument]) -> List[Tuple[KBDocument, KBDocument]]:
    """组内**跨不同 origin** 的两两对(同 origin 对不算跨源,排除)。"""
    pairs: List[Tuple[KBDocument, KBDocument]] = []
    n = len(group)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = group[i], group[j]
            oa, ob = _origin(a), _origin(b)
            if oa == UNKNOWN or ob == UNKNOWN or oa == ob:
                continue  # 需两个已知且不同的 origin
            pairs.append((a, b))
    return pairs


def detect_reconciliation_candidates(
    db: Session, *, actor: str = "detector"
) -> Dict[str, Any]:
    """确定性跨源重叠 detector。**只读 kb_documents、只写候选旁路表;零 serving mutation、零 auto。**

    幂等:已存在的 pair_key 跳过(不复活已 rejected/approved 候选、不改其 status)。
    返回 {created, skipped_existing, truncated, scanned_docs, total_open}。
    """
    docs = db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).all()
    by_hash, by_entity, by_title = _build_buckets(docs)

    # pair -> 触发的信号集合。key 恒为 (lo, hi) = sorted doc_ids。
    pair_signals: Dict[Tuple[str, str], set] = {}
    pair_docs: Dict[Tuple[str, str], Tuple[KBDocument, KBDocument]] = {}
    oversized_buckets = 0

    def _register(a: KBDocument, b: KBDocument, signal: str) -> None:
        lo, hi = sorted((a.doc_id, b.doc_id))
        key = (lo, hi)
        pair_signals.setdefault(key, set()).add(signal)
        if key not in pair_docs:
            # 存成 (lo_doc, hi_doc) 顺序稳定
            pair_docs[key] = (a, b) if a.doc_id == lo else (b, a)

    def _process(buckets, signal: str) -> None:
        nonlocal oversized_buckets
        for group in buckets:
            # 桶级 O(n²) 上界:病态大簇不逐对展开(fail-loud 计数,不静默爆内存)。
            if len(group) > _MAX_BUCKET_SIZE:
                oversized_buckets += 1
                continue
            for a, b in _cross_origin_pairs(group):
                _register(a, b, signal)

    _process(by_hash.values(), "content_hash")
    _process(by_entity.values(), "entity_id")
    _process(by_title.values(), "normalized_title")

    # 幂等:有序对 (left, right) 复合唯一。已存在(含已 rejected)一律跳过,不复活、不重复。
    existing = {
        (row.left_doc_id, row.right_doc_id)
        for row in db.query(
            KBReconciliationCandidate.left_doc_id, KBReconciliationCandidate.right_doc_id
        ).all()
    }

    created = 0
    skipped = 0
    truncated = False
    for (lo, hi), signals in sorted(pair_signals.items()):
        if (lo, hi) in existing:
            skipped += 1
            continue
        left, right = pair_docs[(lo, hi)]
        kind = _kind_for(left, right)
        if kind is None:
            skipped += 1  # entity × claim 混合,不成对
            continue
        if created >= _MAX_CANDIDATES_PER_SCAN:
            truncated = True
            break

        canonical_id, canonical_reason = resolve_canonical(left, right)
        score = round(min(1.0, sum(_SIGNAL_WEIGHTS[s] for s in signals)), 3)
        # 确定性层只在 content_hash 完全相同(字节同内容)时敢标 duplicate;弱信号留 NULL 待 judge。
        relation_tag = "duplicate" if "content_hash" in signals else None

        db.add(
            KBReconciliationCandidate(
                kind=kind,
                left_doc_id=lo,   # = left.doc_id(排序后 min)
                right_doc_id=hi,  # = right.doc_id(排序后 max)
                entity_type=str(left.entity_type or right.entity_type or UNKNOWN),
                entity_id=left.entity_id or right.entity_id,
                relation_tag=relation_tag,
                score=score,
                signals={
                    "detectors": sorted(signals),
                    "detected_by": actor,
                    "left": {"origin": _origin(left), "review_status": _review_status(left), "doc_type": left.doc_type},
                    "right": {"origin": _origin(right), "review_status": _review_status(right), "doc_type": right.doc_type},
                    "canonical_reason": canonical_reason,
                },
                canonical_hint=canonical_id,
                status="open",
            )
        )
        existing.add((lo, hi))
        created += 1

    db.commit()

    total_open = (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.status == "open")
        .count()
    )
    return {
        "created": created,
        "skipped_existing": skipped,
        "truncated": truncated,
        "oversized_buckets": oversized_buckets,
        "scanned_docs": len(docs),
        "total_open": total_open,
    }


def list_reconciliation_candidates(
    db: Session,
    *,
    status: Optional[str] = "open",
    kind: Optional[str] = None,
    relation_tag: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """只读队列。默认列 open 候选,可按 status/kind/relation_tag 过滤。"""
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    q = db.query(KBReconciliationCandidate)
    if status:
        q = q.filter(KBReconciliationCandidate.status == status)
    if kind:
        q = q.filter(KBReconciliationCandidate.kind == kind)
    if relation_tag:
        q = q.filter(KBReconciliationCandidate.relation_tag == relation_tag)
    total = q.count()
    rows = (
        q.order_by(
            KBReconciliationCandidate.score.desc().nullslast(),
            KBReconciliationCandidate.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "candidates": [_candidate_dict(r) for r in rows],
    }


def _candidate_dict(row: KBReconciliationCandidate) -> Dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "left_doc_id": row.left_doc_id,
        "right_doc_id": row.right_doc_id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "relation_tag": row.relation_tag,
        "score": row.score,
        "signals": row.signals or {},
        "canonical_hint": row.canonical_hint,
        "status": row.status,
        "detected_at": row.detected_at.isoformat() if row.detected_at else None,
        "reviewed_by": row.reviewed_by,
    }
