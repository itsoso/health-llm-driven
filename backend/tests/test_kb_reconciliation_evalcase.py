"""KB 对账:eval_case(gold 夹具)必须排除在对账之外(prod 实测 42% 候选是 eval_case 噪声/污染风险)。

双保险:detector 从源头不产 eval_case 候选;merge 侧对任一侧 eval_case 硬拒(挡住修 detector 前遗留候选)。
"""
import pytest

from app.models.system_knowledge import KBDocument, KBReconciliationCandidate
from app.services.kb_reconciliation import detect_reconciliation_candidates
from app.services.kb_reconciliation_merge import can_merge, merge_candidate

DOWN = "down-dedao-llm-wiki"
KBASE = "dedao-kbase-export"


def _doc(db, doc_id, *, doc_type="claim", entity_type="condition", origin=DOWN,
         review_status="reviewed", title="x", aliases=None, content_hash=None):
    meta = {"origin": origin, "review_status": review_status}
    if aliases is not None:
        meta["aliases"] = aliases
    db.add(KBDocument(doc_id=doc_id, doc_type=doc_type, entity_type=entity_type,
                      title=title, content_hash=content_hash, is_archived=False, metadata_json=meta))
    db.commit()


def test_detector_excludes_eval_case_docs(db):
    """claim ↔ 同名 eval_case(gold 夹具)—— 结构上会配对,但 detector 必须从源头排除 eval_case。"""
    # 用 content_hash 完全相同,保证若不排除就会成 duplicate 候选
    _doc(db, "c:brca1", doc_type="claim", origin=DOWN, content_hash="h1", title="BRCA1 DTC 确认边界")
    _doc(db, "eval:brca1", doc_type="eval_case", origin=KBASE, review_status="draft",
         content_hash="h1", title="BRCA1 DTC 确认边界")
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 0  # eval_case 被排除 → 零候选
    assert db.query(KBReconciliationCandidate).count() == 0


def test_detector_still_pairs_two_real_claims(db):
    """对照:两个真 claim(非 eval_case)同 hash 跨源 → 正常产候选(证排除只针对 eval_case)。"""
    _doc(db, "c:a", doc_type="claim", origin=DOWN, content_hash="h1", title="claimA")
    _doc(db, "c:b", doc_type="claim", origin=KBASE, review_status="draft", content_hash="h1", title="claimA")
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 1


def test_merge_hard_rejects_eval_case_belt(db):
    """belt:即便遗留了一个牵涉 eval_case 的候选,merge 也硬拒(护 gold eval 集)。"""
    _doc(db, "c:x", doc_type="claim", origin=DOWN, content_hash="h1", title="X")
    _doc(db, "eval:x", doc_type="eval_case", origin=KBASE, review_status="draft", content_hash="h1", title="X")
    # 手工塞一个候选(模拟修 detector 前遗留)
    c = KBReconciliationCandidate(kind="claim_overlap", left_doc_id="c:x", right_doc_id="eval:x",
                                  relation_tag="duplicate", status="open", signals={})
    db.add(c)
    db.commit()
    ok, reason, _ = can_merge(db, db.query(KBReconciliationCandidate).filter_by(id=c.id).first())
    assert ok is False and "eval_case" in reason
    with pytest.raises(ValueError):
        merge_candidate(db, c.id, actor="admin:1")
