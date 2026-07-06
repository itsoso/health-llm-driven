"""System KB V2 跨源对账 —— Phase B P4:人工 merge + unalign(首个 serving mutation)。

**边界**:只有**人的 approve**(或 P5 过 9 闸的 auto)才调 `merge_candidate`。R4/治理不变量:
- **additive only**:loser 得 `merged_into` + `is_archived=True`(掉出 serving),别名/来源折进 canonical,
  旧边留存 + `superseded_by_align`;**永不物理删** doc/edge。count 不变量:archived+active 恒定。
- **conflict / prescriptive 硬拒**(I4):人机同拒,走人工 conflict-review,不 fold-merge。
- **canonical 由 D1 定**(down-dedao reviewed 恒赢);无 reviewed 锚 → 拒(走人)。
- **license fail-closed 最严**:canonical 取两侧最严 scope,未知当最严;结构上永不放宽(strictest≥自身)。
- **unalign 字节往返可逆**:merge 前把 loser/canonical 的**完整** metadata_json + is_archived 快照进
  candidate.decision;unalign 逐字节还原 + 删新边 + 摘 superseded 标记。P5 auto 的 C9(可逆)依赖它。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument, KBEdge, KBReconciliationCandidate
from app.services.drug_lexicon import prescriptive_free_text_terms
from app.services.kb_reconciliation import _norm_title, resolve_canonical
from app.services.personal_models.intervention_priors import is_clinician_gated_metric

# license 严格序(founder ratified:internal 最严;未知 → 当最严 fail-closed)。
_LICENSE_RANK = {
    "internal_transformed_claims": 3,
    "licensed_transformed_content": 2,
    "public_reference": 1,
}
_UNKNOWN_LICENSE_RANK = 99  # 未知 scope 当最严(绝不因未知而放宽)

# 处方式 entity_type(I4 硬拒地板;claim 的 predicate 另经 is_clinician_gated_metric)。
_PRESCRIPTIVE_ENTITY_TYPES = frozenset(
    {"medication", "drug", "supplement", "diet", "nutrient", "dose", "dosage"}
)

# 剂量正则 —— 数字 + 单位/频次(在**保留空白的小写文本**上匹配,如 "5 mg"/"每日5g"/"once daily")。
import re as _re
_DOSE_RE = _re.compile(
    r"\d+\s*(mg|g|mcg|µg|ug|iu|ml)\b|"        # 拉丁单位加 \b,不误伤 "5 goals"
    r"\d+\s*(片|粒|毫克|克|微克|国际单位)|"      # CJK 单位无词边界语义
    r"\b(qd|bid|tid|qid)\b|每日\d|每天\d|一日\d",  # 频次锚定,避免泛匹配
    _re.IGNORECASE,
)
# 处方/药名锚点集(中英,is_clinician_gated_metric 是化验指标形、**不含药名**,这里补齐 I4 地板)。
# R4 保守:命中即拒走人工;宁可 over-refuse(多进人工队列)也不 under-gate 药物安全语义。
#
# **单一事实源**:药名/剂量词库现由 `drug_lexicon.prescriptive_free_text_terms()` 派生自
# SafetyGuardian 的 ddi/dsi 药名库 + 常见药补集(消除本文件曾手抄一份会漂移的副本)。往安全词库
# 加药名 → 自动进本 gate。旧「~25 命名高危药地板」的残余(布洛芬/氨氯地平/阿莫西林/左甲状腺素/
# lisinopril 等未列名药漏 gate)由此**大幅收窄**;派生集对自由文本去了歧义短子串(钙/铁/iron/pril…),
# 保持 over-refuse 偏向的同时不误伤良性 claim(见 test_nonprescriptive_claim_still_merges)。
# **仍非** 100% 通用药名探测器(食物/草药类刻意不入 gate;极冷门药可能仍漏)—— 但 P4 是人工合并、
# P5 auto 对 药/补剂 claim_overlap 一律不自动(§10 #2),残余不触自动路径。


def _prescriptive_text_blob(doc: KBDocument) -> str:
    parts = [doc.title or "", doc.summary or ""]
    parts.extend(str(x) for x in _aliases(doc))
    if doc.body:
        parts.append(str(doc.body)[:1000])
    return " ".join(parts).lower()  # 保留空白(dose 正则要),仅小写


def _is_prescriptive_text(doc: KBDocument) -> bool:
    """内容层药名/剂量识别 —— 堵住 entity_type=claim/article/None 的药物剂量 claim 漏 gate(I4)。"""
    blob = _prescriptive_text_blob(doc)
    if not blob.strip():
        return False
    if _DOSE_RE.search(blob):
        return True
    return any(term in blob for term in prescriptive_free_text_terms())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta(doc: KBDocument) -> Dict[str, Any]:
    return dict(doc.metadata_json or {})


def _aliases(doc: KBDocument) -> list:
    raw = (doc.metadata_json or {}).get("aliases")
    return list(raw) if isinstance(raw, list) else []


def _license(doc: KBDocument) -> str:
    return str((doc.metadata_json or {}).get("license_scope") or "")


def _license_rank(scope: str) -> int:
    return _LICENSE_RANK.get(scope, _UNKNOWN_LICENSE_RANK)


def _strictest_license(a: str, b: str) -> str:
    """取更严的 scope(rank 高者);相等取 a。未知 rank=99 → 当最严。"""
    return a if _license_rank(a) >= _license_rank(b) else b


def _is_prescriptive(doc: KBDocument) -> bool:
    et = (doc.entity_type or "").lower()
    if et in _PRESCRIPTIVE_ENTITY_TYPES:
        return True
    # 化验指标门控(is_clinician_gated_metric 是指标形,不含药名)。
    for probe in (doc.entity_id or "", _norm_title(doc.title)):
        if probe and is_clinician_gated_metric(probe):
            return True
    # 内容层:药名 + 剂量 —— 堵住 entity_type=claim/article/None 的处方 claim 漏 gate(I4)。
    return _is_prescriptive_text(doc)


def _sides(
    db: Session, cand: KBReconciliationCandidate
) -> Tuple[Optional[KBDocument], Optional[KBDocument]]:
    left = db.query(KBDocument).filter(KBDocument.doc_id == cand.left_doc_id).first()
    right = db.query(KBDocument).filter(KBDocument.doc_id == cand.right_doc_id).first()
    return left, right


def can_merge(
    db: Session, cand: KBReconciliationCandidate
) -> Tuple[bool, str, Optional[str]]:
    """合并前置闸(人机共用)。返回 (ok, reason, canonical_doc_id)。

    ok=False 的原因是**硬拒**(端点映射 400/422),不静默放行。
    """
    if cand.status != "open":
        return False, f"candidate status={cand.status} (只 open 可合并)", None
    left, right = _sides(db, cand)
    if left is None or right is None:
        return False, "端点文档缺失(可能已被归档/删)", None
    # belt-and-suspenders:eval_case 是 gold 夹具,任一侧命中 → 硬拒(护住 gold eval 集不被合污染;
    # 修 detector 前遗留的 eval_case 候选也被这道挡住)。
    if "eval_case" in ((left.doc_type or ""), (right.doc_type or "")):
        return False, "eval_case gold 夹具不可合并(护 gold eval 集)", None
    if cand.relation_tag == "conflict":
        return False, "conflict → 人工 conflict-review,merge 硬拒(I4)", None
    if _is_prescriptive(left) or _is_prescriptive(right):
        return False, "处方式(药/补剂/剂量)→ 人工,merge 硬拒(I4)", None
    canonical_id, reason = resolve_canonical(left, right)
    if canonical_id is None:
        return False, f"无 reviewed down-dedao 锚 → 走人({reason})", None
    return True, "ok", canonical_id


def merge_candidate(
    db: Session, candidate_id: int, *, actor: str
) -> Dict[str, Any]:
    """人工 approve 合并:loser 折进 canonical(additive + 可逆)。**唯一** serving mutation 入口。"""
    cand = (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.id == candidate_id)
        .first()
    )
    if cand is None:
        raise ValueError("candidate 不存在")
    ok, reason, canonical_id = can_merge(db, cand)
    if not ok:
        raise ValueError(reason)

    left, right = _sides(db, cand)
    canonical = left if left.doc_id == canonical_id else right
    loser = right if canonical is left else left

    # ── 反向清单:merge 前**完整快照**(保证 unalign 字节还原)──
    reverse: Dict[str, Any] = {
        "canonical_doc_id": canonical.doc_id,
        "loser_doc_id": loser.doc_id,
        "loser_meta_before": _meta(loser),
        "loser_archived_before": bool(loser.is_archived),
        "canonical_meta_before": _meta(canonical),
        "new_edge_ids": [],
        "superseded_edges": [],  # [{id, meta_before}] —— 字节还原旧边(含 NULL)
        "merged_at": _now_iso(),
    }

    def _supersede(edge: KBEdge) -> None:
        # 先存原样(可能是 None)再打标 —— unalign 逐字节还原,不把 NULL 漂成 {}。
        reverse["superseded_edges"].append({"id": edge.edge_id, "meta_before": edge.metadata_json})
        em = dict(edge.metadata_json or {})
        em["superseded_by_align"] = cand.id
        edge.metadata_json = em

    # ── loser:additive 标记 + 归档(掉出 serving)──
    loser_meta = _meta(loser)
    loser_meta["merged_into"] = canonical.doc_id
    loser_meta["review_status"] = "archived"
    loser.metadata_json = loser_meta  # 整体重赋值(JSONB 变更才被 flush)
    loser.is_archived = True

    # ── canonical:别名 ∪、来源并、license 收严(绝不放宽);body/summary/review_status 不动 ──
    can_meta = _meta(canonical)
    merged_aliases = list(dict.fromkeys(
        _aliases(canonical) + _aliases(loser) + ([loser.title] if loser.title else [])
    ))
    can_meta["aliases"] = merged_aliases
    strict = _strictest_license(_license(canonical), _license(loser))
    if strict:
        can_meta["license_scope"] = strict  # strictest ≥ 自身,结构上永不放宽
    lineage = list(can_meta.get("provenance_lineage") or [])
    lineage.append({
        "folded_doc_id": loser.doc_id,
        "origin": (loser.metadata_json or {}).get("origin"),
        "license_scope": _license(loser),
        "folded_at": reverse["merged_at"],
        "folded_by": actor,
    })
    can_meta["provenance_lineage"] = lineage
    canonical.metadata_json = can_meta

    # ── loser 关联边重指 canonical(旧边留 + superseded_by_align;新边去重)──
    existing_keys = {
        (e.src_doc_id, e.relation, e.dst_doc_id)
        for e in db.query(KBEdge).all()
    }
    touching = (
        db.query(KBEdge)
        .filter((KBEdge.src_doc_id == loser.doc_id) | (KBEdge.dst_doc_id == loser.doc_id))
        .all()
    )
    for e in touching:
        new_src = canonical.doc_id if e.src_doc_id == loser.doc_id else e.src_doc_id
        new_dst = canonical.doc_id if e.dst_doc_id == loser.doc_id else e.dst_doc_id
        if new_src == new_dst:
            # 自环(loser↔canonical 之间的边)→ 不重指,只标 superseded
            _supersede(e)
            continue
        key = (new_src, e.relation, new_dst)
        if key not in existing_keys:
            ne = KBEdge(src_doc_id=new_src, dst_doc_id=new_dst, relation=e.relation,
                        metadata_json={"created_by_align": cand.id, "source_claim_id": e.source_claim_id})
            db.add(ne)
            db.flush()  # 拿 edge_id 存进 reverse 以便 unalign 删除
            reverse["new_edge_ids"].append(ne.edge_id)
            existing_keys.add(key)
        _supersede(e)

    # ── candidate:approved + 反向清单 ──
    cand.status = "approved"
    cand.reviewed_by = actor
    cand.reviewed_at = datetime.now(timezone.utc)
    cand.decision = reverse

    op = "entity_align_approved" if cand.kind == "entity_align" else "claim_merge_source_folded"
    from app.models.system_knowledge import KBAudit
    db.add(KBAudit(doc_id=canonical.doc_id, op=op, actor=actor, diff={
        "candidate_id": cand.id, "canonical": canonical.doc_id, "folded": loser.doc_id,
        "edges_repointed": len(reverse["new_edge_ids"]),
        "edges_superseded": len(reverse["superseded_edges"]),
    }))
    db.commit()
    return {
        "merged": True, "candidate_id": cand.id,
        "canonical": canonical.doc_id, "folded": loser.doc_id,
        "edges_repointed": len(reverse["new_edge_ids"]),
    }


def unalign_candidate(db: Session, candidate_id: int, *, actor: str) -> Dict[str, Any]:
    """撤销一次 merge:逐字节还原 loser/canonical metadata + 删新边 + 摘 superseded 标记。"""
    cand = (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.id == candidate_id)
        .first()
    )
    if cand is None:
        raise ValueError("candidate 不存在")
    if cand.status != "approved" or not cand.decision:
        raise ValueError(f"candidate status={cand.status} 无可撤销的 merge 清单")
    rev = cand.decision
    canonical_id = rev["canonical_doc_id"]

    # ── LIFO 守卫:canonical_meta_before 是**绝对**快照,只有撤销「折入同一 canonical 的最晚一次
    #    merge」才字节正确。若存在更晚的、折入同一 canonical 的 approved 合并,先撤它,否则本次
    #    还原会覆盖那次的 fold(orphan)。fail-loud 拒,绝不静默毁数据。──
    for other in (
        db.query(KBReconciliationCandidate)
        .filter(KBReconciliationCandidate.status == "approved",
                KBReconciliationCandidate.id != cand.id)
        .all()
    ):
        od = other.decision or {}
        if od.get("canonical_doc_id") != canonical_id:
            continue
        o_t, my_t = other.reviewed_at, cand.reviewed_at
        later = (o_t and my_t and o_t > my_t) or (o_t == my_t and other.id > cand.id)
        if later:
            raise ValueError(
                f"存在更晚折入同一 canonical={canonical_id} 的已合并候选 (id={other.id});"
                f"须按 LIFO 先撤销它,否则 canonical 快照还原会覆盖其合并"
            )

    loser = db.query(KBDocument).filter(KBDocument.doc_id == rev["loser_doc_id"]).first()
    canonical = db.query(KBDocument).filter(KBDocument.doc_id == canonical_id).first()
    if loser is None or canonical is None:
        raise ValueError("端点文档缺失,无法安全 unalign")

    # 字节还原(整体重赋值)
    loser.metadata_json = dict(rev["loser_meta_before"])
    loser.is_archived = bool(rev["loser_archived_before"])
    canonical.metadata_json = dict(rev["canonical_meta_before"])

    # 删掉 merge 新建的边
    for eid in rev.get("new_edge_ids", []):
        e = db.query(KBEdge).filter(KBEdge.edge_id == eid).first()
        if e is not None:
            db.delete(e)
    # 旧边**逐字节还原**(含 NULL → 不漂成 {});超集兼容旧 superseded_edge_ids 格式
    for se in rev.get("superseded_edges", []):
        e = db.query(KBEdge).filter(KBEdge.edge_id == se["id"]).first()
        if e is not None:
            e.metadata_json = se["meta_before"]
    for eid in rev.get("superseded_edge_ids", []):  # 向后兼容(不产生新此格式)
        e = db.query(KBEdge).filter(KBEdge.edge_id == eid).first()
        if e is not None:
            em = dict(e.metadata_json or {}); em.pop("superseded_by_align", None)
            e.metadata_json = em

    merged_by = cand.reviewed_by  # 重置前抓原合并者(auto=JUDGE_ACTOR)→ 熔断按此圈定误合
    cand.status = "open"
    cand.reviewed_by = None
    cand.reviewed_at = None
    cand.decision = {"unaligned_at": _now_iso(), "unaligned_by": actor, "prior": rev}

    from app.models.system_knowledge import KBAudit
    db.add(KBAudit(doc_id=canonical.doc_id, op="entity_align_unaligned", actor=actor, diff={
        "candidate_id": cand.id, "restored_loser": loser.doc_id, "merged_by": merged_by,
    }))
    db.commit()
    return {"unaligned": True, "candidate_id": cand.id}
