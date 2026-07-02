"""System KB V2 跨源对账 —— Phase B P5 eval:测 judge/auto 精度 + 6 条不变量断言。

Founder ratified τ=0.95 是 gate(非逐 type 零 FP);eval **不再硬 gate 但仍必跑**(§10):
- 测 judge 分类 + can_auto_approve 的 precision/recall(auto FP 是最关心的——无人误合)。
- 对「会 auto-fire」的候选真跑 merge + 6 条不变量断言 + unalign 还原,证 auto 路径安全可逆。

gold label 存在 candidate.signals['gold_label'] ∈ {'duplicate','not_duplicate'}(测试/授权 fixture 填)。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument, KBReconciliationCandidate
from app.services.kb_reconciliation_judge import (
    can_auto_approve,
    classify_candidate,
)
from app.services.kb_reconciliation_merge import merge_candidate, unalign_candidate


def run_dedup_judge_eval(
    db: Session,
    *,
    classifier: Optional[Callable] = None,
    enabled_entity_types: frozenset = frozenset(),
) -> Dict[str, Any]:
    """对带 gold_label 的候选跑 judge + can_auto_approve,measure precision/recall。**不改 serving**(只 judge)。

    precision 分母 = 会 auto-fire 的数;FP = auto-fire 但 gold 非 duplicate(最危险,无人误合)。
    """
    labeled = [
        c for c in db.query(KBReconciliationCandidate).filter(
            KBReconciliationCandidate.status == "open"
        ).all()
        if (c.signals or {}).get("gold_label") in ("duplicate", "not_duplicate")
    ]
    tp = fp = fn = tn = 0
    fp_examples: List[Dict[str, Any]] = []
    for c in labeled:
        gold_dup = (c.signals or {}).get("gold_label") == "duplicate"
        classify_candidate(db, c, classifier=classifier)
        would_fire, _reasons = can_auto_approve(db, c, enabled_entity_types=enabled_entity_types)
        if would_fire and gold_dup:
            tp += 1
        elif would_fire and not gold_dup:
            fp += 1
            fp_examples.append({"candidate_id": c.id, "gold": "not_duplicate", "judged": c.relation_tag, "score": c.score})
        elif not would_fire and gold_dup:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {
        "n": len(labeled),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": precision,
        "recall": recall,
        "auto_approve_fp": fp,  # 核心安全指标:无人误合数(理想 0)
        "fp_examples": fp_examples,
    }


def check_merge_invariants(db: Session, candidate_id: int, *, actor: str = "eval") -> Dict[str, bool]:
    """对一条候选真跑 merge → 断言 6 不变量 → unalign 还原。返回 {invariant: passed}。

    证 auto 路径的 merge 安全可逆;跑在 eval/测试 DB 上(会 merge 再 unalign,净零副作用)。
    """
    from app.services.system_knowledge_service import _serving_document_filters

    cand = db.query(KBReconciliationCandidate).filter_by(id=candidate_id).first()
    left = db.query(KBDocument).filter_by(doc_id=cand.left_doc_id).first()
    right = db.query(KBDocument).filter_by(doc_id=cand.right_doc_id).first()

    doc_count_before = db.query(KBDocument).count()
    canon_meta_before = {
        left.doc_id: dict(left.metadata_json or {}),
        right.doc_id: dict(right.metadata_json or {}),
    }
    canon_license_before = {
        d.doc_id: (d.metadata_json or {}).get("license_scope") for d in (left, right)
    }

    res = merge_candidate(db, candidate_id, actor=actor)
    db.expire_all()
    canonical = db.query(KBDocument).filter_by(doc_id=res["canonical"]).first()
    loser = db.query(KBDocument).filter_by(doc_id=res["folded"]).first()

    checks: Dict[str, bool] = {}
    # 1 count 不变量(归档不删)
    checks["count_invariant"] = db.query(KBDocument).count() == doc_count_before
    # 2 canonical 是 down-dedao reviewed(D1)
    checks["canonical_is_down_dedao_reviewed"] = (
        (canonical.metadata_json or {}).get("origin") == "down-dedao-llm-wiki"
        and (canonical.metadata_json or {}).get("review_status") == "reviewed"
    )
    # 3 loser 掉出 serving,canonical 仍服务(no-unreviewed-served)
    served_loser = db.query(KBDocument).filter(
        KBDocument.doc_id == loser.doc_id, *_serving_document_filters()
    ).first()
    served_canon = db.query(KBDocument).filter(
        KBDocument.doc_id == canonical.doc_id, *_serving_document_filters()
    ).first()
    checks["loser_out_of_serving"] = served_loser is None
    checks["canonical_still_served"] = served_canon is not None
    # 4 canonical content 未改(review_status)
    checks["canonical_review_status_unchanged"] = (
        (canonical.metadata_json or {}).get("review_status") == "reviewed"
    )
    # 5 license 不放宽(canonical 现 license rank ≥ 原 rank)
    from app.services.kb_reconciliation_merge import _license_rank
    checks["license_not_widened"] = (
        _license_rank((canonical.metadata_json or {}).get("license_scope") or "")
        >= _license_rank(canon_license_before.get(canonical.doc_id) or "")
    )

    # 6 unalign 字节还原
    unalign_candidate(db, candidate_id, actor=actor)
    db.expire_all()
    l2 = db.query(KBDocument).filter_by(doc_id=left.doc_id).first()
    r2 = db.query(KBDocument).filter_by(doc_id=right.doc_id).first()
    checks["unalign_byte_restore"] = (
        dict(l2.metadata_json or {}) == canon_meta_before[left.doc_id]
        and dict(r2.metadata_json or {}) == canon_meta_before[right.doc_id]
    )
    return checks
