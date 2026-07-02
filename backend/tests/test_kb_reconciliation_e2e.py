"""KB Phase-B 端到端集成:真 detector → judge → can_auto_approve → merge → unalign → 粘性熔断。

各层单测各测一层(候选多为直接构造)。本测**从真文档跑整条管线**,锁住跨阶段接缝:
- detector 写的 signals['detectors'] 能否被 can_auto_approve / _strong_signal_conjunction 读到;
- judge 写 signals['judge'] 不冲掉 detectors;
- merge 的 reverse manifest 活到 unalign;熔断读 unalign 的 merged_by;serving 门反映归档。

关键安全断言:**即便 judge 对所有对都说 duplicate 0.99**,服务端硬闸只放行该放行的那一对
(别名重复 auto 合),而冲突对(状态反义)+ 处方对被硬拒走人。
"""
from app.models.system_knowledge import KBDocument, KBReconciliationCandidate
from app.services.kb_reconciliation import detect_reconciliation_candidates
from app.services.kb_reconciliation_judge import (
    JUDGE_ACTOR,
    auto_breaker_status,
    can_auto_approve,
    reset_auto_breaker,
    run_judge_and_auto,
)
from app.services.kb_reconciliation_merge import unalign_candidate
from app.services.system_knowledge_service import _serving_document_filters

DOWN = "down-dedao-llm-wiki"
KBASE = "dedao-kbase-export"


def _doc(db, doc_id, *, entity_type="condition", origin=DOWN, review_status="reviewed",
         title="x", aliases=None, doc_type="entity"):
    meta = {"origin": origin, "review_status": review_status}
    if aliases is not None:
        meta["aliases"] = aliases
    db.add(KBDocument(doc_id=doc_id, doc_type=doc_type, entity_type=entity_type,
                      title=title, is_archived=False, metadata_json=meta))
    db.commit()


def _served(db, doc_id):
    return (db.query(KBDocument)
            .filter(KBDocument.doc_id == doc_id, *_serving_document_filters()).first())


# 判 duplicate 0.99 对所有对(最激进 judge)—— 用来证服务端硬闸才是真安全。
def _judge_all_duplicate(left, right):
    return {"relation_tag": "duplicate", "score": 0.99, "rationale": "aggressive"}


def test_full_pipeline_only_safe_pair_auto_merges(db):
    # Pair A(应 auto 合):别名重复,低危 condition,disjoint 词表 alfa/beta
    _doc(db, "dd:A", entity_type="condition", origin=DOWN, review_status="reviewed",
         title="幽门螺杆菌感染", aliases=["alfaTok", "betaTok"])
    _doc(db, "kb:A", entity_type="condition", origin=KBASE, review_status="draft",
         title="Hp感染", aliases=["alfaTok", "betaTok"])
    # Pair B(应硬拒:状态反义冲突 C6b),disjoint 词表 gamma/delta;antonym 只在 title
    _doc(db, "dd:B", entity_type="condition", origin=DOWN, review_status="reviewed",
         title="抗体阳性", aliases=["gammaTok", "deltaTok"])
    _doc(db, "kb:B", entity_type="condition", origin=KBASE, review_status="draft",
         title="抗体阴性", aliases=["gammaTok", "deltaTok"])
    # Pair C(应硬拒:处方类 medication),disjoint 词表 eps/zeta
    _doc(db, "dd:C", entity_type="medication", origin=DOWN, review_status="reviewed",
         title="药物X", aliases=["epsTok", "zetaTok"])
    _doc(db, "kb:C", entity_type="medication", origin=KBASE, review_status="draft",
         title="drugX", aliases=["epsTok", "zetaTok"])

    # ── 1. 真 detector:各对 2 个共享 alias token → 恰 3 个 entity_align 候选,relation_tag 空 ──
    scan = detect_reconciliation_candidates(db)
    assert scan["created"] == 3
    cands = {tuple(sorted((c.left_doc_id, c.right_doc_id))): c
             for c in db.query(KBReconciliationCandidate).all()}
    assert ("dd:A", "kb:A") in cands and ("dd:B", "kb:B") in cands and ("dd:C", "kb:C") in cands
    for c in cands.values():
        assert c.kind == "entity_align"
        assert c.relation_tag is None  # 无 content_hash → 待判
        assert "alias_overlap" in c.signals["detectors"]  # 接缝:detector 写的 signals

    # ── 2. 全管线跑 auto(judge 对所有对都说 duplicate 0.99;只启用 condition)──
    res = run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset({"condition"}),
                             classifier=_judge_all_duplicate)
    assert res["judged"] == 3
    assert res["auto_merged"] == 1        # 只有 Pair A(安全对)
    assert res["left_for_human"] == 2     # B(冲突)+ C(处方)硬拒

    # ── 3. Pair A:loser 归档掉出 serving,canonical 内容不变仍服务(接缝:serving 门)──
    db.expire_all()
    assert _served(db, "kb:A") is None
    canon = _served(db, "dd:A")
    assert canon is not None and canon.metadata_json["review_status"] == "reviewed"
    assert "alfaTok" in canon.metadata_json["aliases"]  # 别名并入
    cand_a = cands[("dd:A", "kb:A")]
    assert db.query(KBReconciliationCandidate).filter_by(id=cand_a.id).first().status == "approved"

    # ── 4. Pair B/C:未合并,仍 open,draft 未被归档 ──
    for pair in (("dd:B", "kb:B"), ("dd:C", "kb:C")):
        c = db.query(KBReconciliationCandidate).filter_by(id=cands[pair].id).first()
        assert c.status == "open"
    assert db.query(KBDocument).filter_by(doc_id="kb:B").first().is_archived is False

    # ── 5. 人工 unalign Pair A(判为误合)→ 字节还原 + 粘性熔断 trip(接缝:unalign→breaker)──
    unalign_candidate(db, cand_a.id, actor="admin:9")
    db.expire_all()
    assert db.query(KBDocument).filter_by(doc_id="kb:A").first().is_archived is False  # 还原
    assert _served(db, "kb:A") is None  # 仍是 draft(不服务),但不再是 archived
    b = auto_breaker_status(db)
    assert b["tripped"] is True and b["detected_fp"] == 1

    # ── 6. 熔断中:再扫再判,C10 拦下一切 auto(即便 Pair A 现在回到 open+可合)──
    res2 = run_judge_and_auto(db, actor="admin:1", enabled_entity_types=frozenset({"condition"}),
                              classifier=_judge_all_duplicate)
    assert res2["auto_merged"] == 0  # 熔断中零自动合

    # ── 7. 审计化人工 reset → auto 恢复 ──
    reset_auto_breaker(db, actor="admin:9", note="已复核:Pair A 实为不同实体,回滚正确")
    assert auto_breaker_status(db)["tripped"] is False
    cand_a2 = db.query(KBReconciliationCandidate).filter_by(id=cand_a.id).first()
    ok, reasons = can_auto_approve(db, cand_a2, enabled_entity_types=frozenset({"condition"}))
    assert ok is True, reasons  # reset 后可再 auto


def test_full_pipeline_disabled_by_default_only_judges(db):
    """默认(空 enabled)整条管线只 judge 不合 —— ships DISABLED 的端到端证。"""
    _doc(db, "dd:x", origin=DOWN, review_status="reviewed", title="实体X", aliases=["xtokA", "xtokB"])
    _doc(db, "kb:x", origin=KBASE, review_status="draft", title="实体X别名", aliases=["xtokA", "xtokB"])
    detect_reconciliation_candidates(db)
    res = run_judge_and_auto(db, actor="admin:1", classifier=_judge_all_duplicate)  # enabled 默认空
    assert res["judged"] == 1 and res["auto_merged"] == 0
    # judge 仍写了 relation_tag(advisory),但没合
    c = db.query(KBReconciliationCandidate).first()
    assert c.status == "open" and c.relation_tag == "duplicate"
