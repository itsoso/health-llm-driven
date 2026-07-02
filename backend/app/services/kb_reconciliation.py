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

detector 信号两类,都只 SURFACE 候选给人工队列(relation_tag 恒 NULL,除非 content_hash 完全相同):
- **结构性**:同 content_hash / 同 entity_id / 归一 title 相同(只有 content_hash 才标 'duplicate')。
- **语义对齐**(edge_neighborhood + alias_overlap):找结构信号抓不到的**别名级**跨源重复
  (Hp vs 幽门螺杆菌 —— 不同 entity_id + 不同 title)。共享 (dir,rel,neighbor) 邻域(IDF 加权、
  超级 hub 跳)+ 共享 title/alias token。**只读 kb_edges(零 mutation)**,永不设 relation_tag。
语义判定(agree/conflict/complementary)与处方地板、任何 merge 一律不在 P3(P5 judge 才做)。
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument, KBEdge, KBReconciliationCandidate
from app.services.system_knowledge_service import _normalize_knowledge_text

DOWN_DEDAO_ORIGIN = "down-dedao-llm-wiki"
UNKNOWN = "unknown"
_ENTITY_DOC_TYPE = "entity"
# eval_case 是**gold eval 夹具**(测 judge/检索用),不是可去重的知识条目。它们与被测的真 claim
# title 高度相似 → 会系统性配对进队列(prod 实测 33 候选里 14 条牵涉 eval_case = 42% 噪声),且一旦
# 被合并会污染 gold eval 集或 serving KB。故对账**从源头排除** eval_case;merge 侧再加一道 belt。
_EXCLUDED_DOC_TYPES = frozenset({"eval_case"})

# 确定性信号权重(纯结构,informational;P5 judge 才定 τ)。
# edge_neighborhood/alias_overlap 是**语义对齐**信号(找 Hp vs 幽门螺杆菌 这类别名级跨源重复,
# 结构信号 content_hash/entity_id/title 抓不到)。两者权重都**低于**任一结构信号,且**永不**设
# relation_tag='duplicate'(那只归 content_hash);只做队列排序提示,语义判定留 P5 judge。
_SIGNAL_WEIGHTS = {
    "content_hash": 0.7,
    "entity_id": 0.5,
    "normalized_title": 0.4,
    "edge_neighborhood": 0.35,
    "alias_overlap": 0.30,
}
_EVIDENCE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}
# 防跑飞:单次扫描最多写这么多候选(863 doc/15 类型下远够;KB 长大后截断而非静默全扫)。
_MAX_CANDIDATES_PER_SCAN = 5000
# 桶级 O(n²) 上界:单个 content_hash/entity_id/title 桶超过这么多文档就**不逐对展开**
# (真跨源重复簇只有几篇;100+ 篇同 hash/同 id 是数据病态 = 批量重复,须 reviewer 整簇看,
# 不是 ~5000 条两两候选)。跳过的桶数在返回 + 审计里 fail-loud 暴露,不静默全扫爆内存。
_MAX_BUCKET_SIZE = 100

# ── 语义对齐信号阈值(P3 无 eval 语料,均为按种子度分布的保守猜测;relation_tag 恒 NULL,
#    调错只影响人工队列噪声,绝不误合。P5 eval harness 起来后重调。) ──
_K_EDGE_OVERLAP = 0.8      # IDF 加权共享邻域重叠和阈值(可调)
_MIN_SHARED_NEIGHBORS = 2  # 至少共享 2 个 (dir,rel,neighbor) —— 单个 hub 永不单独成对(硬地板)
_K_ALIAS_OVERLAP = 2       # 至少共享 2 个非平凡 title/alias token(可调)
# 超级 hub 上界:被 >200 个 entity 触达的 token 是分类根,不展开其 O(m²) 对(fail-loud 计数)。
_MAX_NEIGHBOR_FANOUT = 200
_STOPLIST = {"the", "and", "of", "for", "with", "status", "unknown", "的", "与", "和", "状态", "不明", "未知"}
_TOKEN_SPLIT = re.compile(r"[^0-9a-z一-鿿]+")


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


def _is_cross_origin(a: KBDocument, b: KBDocument) -> bool:
    """两文档 origin 都已知且不同 = 跨源(标量版,供语义 producer 逐对判)。"""
    oa, ob = _origin(a), _origin(b)
    return oa != UNKNOWN and ob != UNKNOWN and oa != ob


def _cross_origin_pairs(group: List[KBDocument]) -> List[Tuple[KBDocument, KBDocument]]:
    """组内**跨不同 origin** 的两两对(同 origin 对不算跨源,排除)。"""
    pairs: List[Tuple[KBDocument, KBDocument]] = []
    n = len(group)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = group[i], group[j]
            if _is_cross_origin(a, b):
                pairs.append((a, b))
    return pairs


def _alias_tokens(doc: KBDocument) -> Tuple[Set[str], bool]:
    """title + metadata.aliases 的归一 token 集。返回 (tokens, malformed)。

    malformed=True:aliases 存在但不是 list(脏数据)→ 调用方 fail-loud 计数,**不静默吞**。
    token = 整条归一串(CJK 安全,不做中文分词)+ 标点切出的片段(len≥2,去 _STOPLIST)。
    """
    strings: List[str] = []
    if doc.title:
        strings.append(str(doc.title))
    malformed = False
    raw_aliases = (doc.metadata_json or {}).get("aliases")
    if raw_aliases is not None:
        if isinstance(raw_aliases, list):
            strings.extend(str(x) for x in raw_aliases)
        else:
            malformed = True  # 非 list → 脏数据,跳过但计数
    tokens: Set[str] = set()
    for s in strings:
        norm = _normalize_knowledge_text(s)
        if len(norm) >= 2 and norm not in _STOPLIST:
            tokens.add(norm)  # 整条归一串作一个 token(CJK 安全)
        for frag in _TOKEN_SPLIT.split(norm):
            if len(frag) >= 2 and frag not in _STOPLIST:
                tokens.add(frag)
    return tokens, malformed


def detect_reconciliation_candidates(
    db: Session, *, actor: str = "detector"
) -> Dict[str, Any]:
    """确定性跨源重叠 detector。**只读 kb_documents、只写候选旁路表;零 serving mutation、零 auto。**

    幂等:已存在的 pair_key 跳过(不复活已 rejected/approved 候选、不改其 status)。
    返回 {created, skipped_existing, truncated, scanned_docs, total_open}。
    """
    docs = (
        db.query(KBDocument)
        .filter(KBDocument.is_archived.is_(False),
                KBDocument.doc_type.notin_(_EXCLUDED_DOC_TYPES))  # gold eval 夹具不参与对账
        .all()
    )
    by_hash, by_entity, by_title = _build_buckets(docs)

    # pair -> 触发的信号集合。key 恒为 (lo, hi) = sorted doc_ids。
    pair_signals: Dict[Tuple[str, str], set] = {}
    pair_docs: Dict[Tuple[str, str], Tuple[KBDocument, KBDocument]] = {}
    pair_evidence: Dict[Tuple[str, str], Dict[str, Any]] = {}  # 语义信号的可审证据(存进 signals JSONB)
    oversized_buckets = 0
    oversized_neighbor_tokens = 0  # 语义:超级 hub token 被跳(fail-loud)
    malformed_alias_docs = 0       # 语义:aliases 非 list 的脏文档被跳(fail-loud)

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

    def _process_semantic_overlap() -> None:
        """语义对齐信号(edge_neighborhood + alias_overlap)—— 找结构信号抓不到的别名级跨源重复。

        **只读 kb_documents(复用 docs)+ kb_edges(仅列查,零 mutation)**。倒排索引 + 桶内共现,
        绝不 O(V²);超级 hub token 按 _MAX_NEIGHBOR_FANOUT 跳(fail-loud)。两信号都**永不**设
        relation_tag(仍恒 NULL),只经 _register 汇进同一累加器。
        """
        nonlocal oversized_neighbor_tokens, malformed_alias_docs
        ent = {d.doc_id: d for d in docs if d.doc_type == _ENTITY_DOC_TYPE}
        if len(ent) < 2:
            return

        # STEP 1:邻域 token N + df(只读 kb_edges,仅列)。token=(dir,rel,neighbor),含方向。
        neigh: Dict[str, Set[Tuple[str, str, str]]] = defaultdict(set)
        edges = db.query(KBEdge.src_doc_id, KBEdge.dst_doc_id, KBEdge.relation).all()
        for src, dst, rel in edges:
            if src in ent:
                neigh[src].add(("out", rel, dst))
            if dst in ent:
                neigh[dst].add(("in", rel, src))

        # STEP 1b:alias/title token T(脏 aliases fail-loud 计数)。
        alias_tok: Dict[str, Set[str]] = {}
        for did, d in ent.items():
            toks, malformed = _alias_tokens(d)
            if malformed:
                malformed_alias_docs += 1
            alias_tok[did] = toks

        # STEP 2+3:倒排索引 + 桶内共现累加(超级 hub 跳)。
        def _accumulate(index_src: Dict[str, Set], weighted: bool):
            nonlocal oversized_neighbor_tokens
            inv: Dict[Any, List[str]] = defaultdict(list)
            for did, toks in index_src.items():
                for t in toks:
                    inv[t].append(did)
            df = {t: len(ids) for t, ids in inv.items()}
            cooc: Dict[Tuple[str, str], float] = defaultdict(float)
            cnt: Counter = Counter()
            for t, ids in inv.items():
                if len(ids) > _MAX_NEIGHBOR_FANOUT:
                    oversized_neighbor_tokens += 1
                    continue  # 超级 hub:不展开 O(m²)
                w = (1.0 / math.log2(1 + df[t])) if weighted else 1.0
                ids_sorted = sorted(ids)
                for i in range(len(ids_sorted)):
                    for j in range(i + 1, len(ids_sorted)):
                        key = (ids_sorted[i], ids_sorted[j])
                        cooc[key] += w
                        cnt[key] += 1
            return cooc, cnt

        edge_cooc, edge_cnt = _accumulate(neigh, weighted=True)
        alias_cooc, alias_cnt = _accumulate(alias_tok, weighted=False)

        # STEP 4:发射。GATE 0 = 两侧 entity(ent 已过滤)+ entity_id 不同 + 跨源。
        candidate_keys = set(edge_cooc) | set(alias_cnt)
        for (lo, hi) in candidate_keys:
            a, b = ent[lo], ent[hi]
            if (a.entity_id or "") == (b.entity_id or "") and a.entity_id:
                continue  # 同 entity_id 已由 entity_id 桶负责
            if not _is_cross_origin(a, b):
                continue
            edge_fires = edge_cnt.get((lo, hi), 0) >= _MIN_SHARED_NEIGHBORS and edge_cooc.get((lo, hi), 0.0) >= _K_EDGE_OVERLAP
            alias_fires = alias_cnt.get((lo, hi), 0) >= _K_ALIAS_OVERLAP
            if not (edge_fires or alias_fires):
                continue
            ev = pair_evidence.setdefault((lo, hi), {})
            if edge_fires:
                _register(a, b, "edge_neighborhood")
                shared = sorted(neigh[lo] & neigh[hi])
                ev["edge_neighborhood"] = {
                    "overlap_score": round(edge_cooc[(lo, hi)], 3),
                    "shared_count": edge_cnt[(lo, hi)],
                    "shared_top": [list(t) for t in shared[:5]],
                }
            if alias_fires:
                _register(a, b, "alias_overlap")
                ev["alias_overlap"] = {
                    "shared_tokens": sorted(alias_tok[lo] & alias_tok[hi])[:20],
                }

    _process(by_hash.values(), "content_hash")
    _process(by_entity.values(), "entity_id")
    _process(by_title.values(), "normalized_title")
    _process_semantic_overlap()

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
        # 确定性层只在 content_hash 完全相同(字节同内容)时敢标 duplicate;弱信号(含语义对齐)留 NULL 待 judge。
        relation_tag = "duplicate" if "content_hash" in signals else None

        signals_blob = {
            "detectors": sorted(signals),
            "detected_by": actor,
            "left": {"origin": _origin(left), "review_status": _review_status(left), "doc_type": left.doc_type},
            "right": {"origin": _origin(right), "review_status": _review_status(right), "doc_type": right.doc_type},
            "canonical_reason": canonical_reason,
        }
        signals_blob.update(pair_evidence.get((lo, hi), {}))  # 语义信号可审证据(edge/alias)

        db.add(
            KBReconciliationCandidate(
                kind=kind,
                left_doc_id=lo,   # = left.doc_id(排序后 min)
                right_doc_id=hi,  # = right.doc_id(排序后 max)
                entity_type=str(left.entity_type or right.entity_type or UNKNOWN),
                entity_id=left.entity_id or right.entity_id,
                relation_tag=relation_tag,
                score=score,
                signals=signals_blob,
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
        "oversized_neighbor_tokens": oversized_neighbor_tokens,
        "malformed_alias_docs": malformed_alias_docs,
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


def list_shadow_pending(db: Session, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """待影子复核的 auto 合(P6)。**全量** approved 里过滤再分页 —— 不做页内过滤
    (页内过滤会把 pending 项埋进后页且 total 虚报 0 = 人环 fail-open,对抗审计抓过)。
    approved+抽中数量本身很小(≤ 每轮 1-2 笔),全量加载有界。"""
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    rows = (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.status == "approved")
        .order_by(KBReconciliationCandidate.id.desc())
        .all()
    )
    pending = [
        r for r in rows
        if ((r.decision or {}).get("shadow_audit") or {}).get("status") == "pending"
    ]
    return {
        "total": len(pending),
        "limit": limit,
        "offset": offset,
        "candidates": [_candidate_dict(r) for r in pending[offset : offset + limit]],
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
        # 影子审计标记(P6 抽样复核;非抽中为 None)。只暴露 flag,不暴露整份 reverse manifest。
        "shadow_audit": (row.decision or {}).get("shadow_audit"),
    }
