"""KB Phase-B P3:跨源对账 detector + 只读队列。

核心不变量(P3 边界):detector **只读 kb_documents、只写候选旁路表**,
**零 serving mutation、零 auto-approve、零 merge**。resolve_canonical 纯函数(D1)。
"""
from app.models.system_knowledge import KBDocument, KBReconciliationCandidate
from app.services.kb_reconciliation import (
    detect_reconciliation_candidates,
    list_reconciliation_candidates,
    resolve_canonical,
)

DOWN = "down-dedao-llm-wiki"
KBASE = "dedao-kbase-export"


def _doc(
    db,
    doc_id,
    *,
    doc_type="claim",
    entity_type="condition",
    entity_id=None,
    content_hash=None,
    title="幽门螺杆菌感染",
    origin=DOWN,
    review_status="reviewed",
    evidence_level="B",
):
    db.add(
        KBDocument(
            doc_id=doc_id,
            doc_type=doc_type,
            entity_type=entity_type,
            entity_id=entity_id,
            title=title,
            content_hash=content_hash,
            evidence_level=evidence_level,
            is_archived=False,
            metadata_json={"origin": origin, "review_status": review_status},
        )
    )
    db.commit()


def test_detector_finds_cross_source_content_hash_duplicate(db):
    _doc(db, "dd:hp", origin=DOWN, review_status="reviewed", content_hash="h1")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", content_hash="h1")
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 1
    rows = db.query(KBReconciliationCandidate).all()
    assert len(rows) == 1
    c = rows[0]
    # content_hash 完全相同 → 确定性可标 duplicate
    assert c.relation_tag == "duplicate"
    # D1:down-dedao reviewed 侧是 canonical hint
    assert c.canonical_hint == "dd:hp"
    assert c.kind == "claim_overlap"
    assert "content_hash" in c.signals["detectors"]
    assert c.status == "open"


def test_detector_zero_serving_mutation(db):
    """最关键的治理测试:detector 绝不动 kb_documents —— draft 仍 draft、reviewed 仍 served。"""
    from app.services.system_knowledge_service import _serving_document_filters

    _doc(db, "dd:hp", origin=DOWN, review_status="reviewed", content_hash="h1")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", content_hash="h1")
    detect_reconciliation_candidates(db)

    draft = db.query(KBDocument).filter(KBDocument.doc_id == "kb:hp").first()
    assert draft.is_archived is False  # 没被 archive
    assert "merged_into" not in (draft.metadata_json or {})  # 没被折
    assert (draft.metadata_json or {}).get("review_status") == "draft"  # review_status 没被改

    # serving 门:draft 仍不服务、reviewed 仍服务(detector 零改变)
    served_draft = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id == "kb:hp", *_serving_document_filters())
        .first()
    )
    assert served_draft is None
    served_reviewed = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id == "dd:hp", *_serving_document_filters())
        .first()
    )
    assert served_reviewed is not None


def test_detector_idempotent(db):
    _doc(db, "dd:hp", origin=DOWN, content_hash="h1")
    _doc(db, "kb:hp", origin=KBASE, review_status="draft", content_hash="h1")
    first = detect_reconciliation_candidates(db)
    assert first["created"] == 1
    second = detect_reconciliation_candidates(db)
    assert second["created"] == 0
    assert second["skipped_existing"] == 1
    assert db.query(KBReconciliationCandidate).count() == 1  # 无重复行


def test_same_origin_pair_is_not_cross_source(db):
    # 两个同 origin(都 dedao-kbase)同 hash → 不是跨源候选,detector 不产
    _doc(db, "kb:a", origin=KBASE, review_status="draft", content_hash="h1")
    _doc(db, "kb:b", origin=KBASE, review_status="draft", content_hash="h1")
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 0
    assert db.query(KBReconciliationCandidate).count() == 0


def test_entity_vs_claim_mixed_pair_skipped(db):
    # 一个 entity 文档 + 一个 claim 文档共享 entity_id → 不成合并对(kind None)
    _doc(db, "dd:ent", doc_type="entity", origin=DOWN, entity_id="e:hp", content_hash=None)
    _doc(db, "kb:clm", doc_type="claim", origin=KBASE, review_status="draft", entity_id="e:hp", content_hash=None)
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 0


def test_weak_signal_leaves_relation_tag_null(db):
    # 同 entity_id 但 content_hash 不同 → 弱信号候选,relation_tag 留 NULL 待 P5 judge
    _doc(db, "dd:hp", doc_type="entity", origin=DOWN, entity_id="e:hp", content_hash="h1", title="幽门螺杆菌")
    _doc(db, "kb:hp", doc_type="entity", origin=KBASE, review_status="draft", entity_id="e:hp", content_hash="h2", title="Hp 细菌")
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 1
    c = db.query(KBReconciliationCandidate).first()
    assert c.relation_tag is None  # 确定性层不敢判 duplicate
    assert c.kind == "entity_align"
    assert "entity_id" in c.signals["detectors"]


def test_resolve_canonical_down_dedao_wins(db):
    dd = KBDocument(doc_id="dd", doc_type="claim", metadata_json={"origin": DOWN, "review_status": "reviewed"})
    kb = KBDocument(doc_id="kb", doc_type="claim", metadata_json={"origin": KBASE, "review_status": "draft"})
    cid, reason = resolve_canonical(dd, kb)
    assert cid == "dd"
    cid2, _ = resolve_canonical(kb, dd)  # 顺序无关
    assert cid2 == "dd"


def test_resolve_canonical_two_drafts_no_anchor(db):
    a = KBDocument(doc_id="a", doc_type="claim", metadata_json={"origin": KBASE, "review_status": "draft"})
    b = KBDocument(doc_id="b", doc_type="claim", metadata_json={"origin": KBASE, "review_status": "draft"})
    cid, reason = resolve_canonical(a, b)
    assert cid is None  # 无 reviewed down-dedao 锚 → 走人,P5 auto 硬拒
    assert "no reviewed" in reason


def test_resolve_canonical_unreviewed_downdedao_no_anchor(db):
    # down-dedao 但未 reviewed → 不算合法 canonical 锚
    dd = KBDocument(doc_id="dd", doc_type="claim", metadata_json={"origin": DOWN, "review_status": "draft"})
    kb = KBDocument(doc_id="kb", doc_type="claim", metadata_json={"origin": KBASE, "review_status": "draft"})
    cid, _ = resolve_canonical(dd, kb)
    assert cid is None


def test_doc_ids_with_separator_do_not_collide(db):
    """对抗回归(原 `||`-join 键歧义 kill):doc_id 含 `||` 时两对必须各存各的,不静默丢。

    {a, b||c} 与 {a||b, c} 曾映射同一字符串键 → 后者被静默跳过(丢真跨源重复)。
    复合唯一 (left,right) 以真 doc_id 为键 → 两对是不同 tuple,各写一行。
    """
    _doc(db, "a", origin=DOWN, content_hash="hX", entity_id=None, title="t1")
    _doc(db, "b||c", origin=KBASE, review_status="draft", content_hash="hX", entity_id=None, title="t2")
    _doc(db, "a||b", origin=DOWN, content_hash="hY", entity_id=None, title="t3")
    _doc(db, "c", origin=KBASE, review_status="draft", content_hash="hY", entity_id=None, title="t4")
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 2  # 两对都在,无碰撞丢失
    pairs = {(r.left_doc_id, r.right_doc_id) for r in db.query(KBReconciliationCandidate).all()}
    assert ("a", "b||c") in pairs
    assert ("a||b", "c") in pairs


def test_oversized_bucket_is_bounded_and_flagged(monkeypatch):
    """对抗回归(cap-after-O(n²) 内存爆):病态大簇不逐对展开,fail-loud 计数暴露。"""
    import app.services.kb_reconciliation as m

    monkeypatch.setattr(m, "_MAX_BUCKET_SIZE", 3)
    # 用一个独立内存库(避免与其它 test 共享),建 4 篇同 hash 跨源 → 超阈值桶被整跳
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    s = S()
    try:
        for i in range(4):
            origin = DOWN if i % 2 == 0 else KBASE
            _doc(s, f"d{i}", origin=origin, review_status="reviewed" if origin == DOWN else "draft", content_hash="hbig")
        res = detect_reconciliation_candidates(s)
        assert res["oversized_buckets"] >= 1
        assert res["created"] == 0  # 超阈值桶不展开 → 零候选(整簇留给 reviewer)
    finally:
        s.close()


def test_scan_write_endpoint_requires_admin(client, auth_user_and_headers):
    """写端点 /reconciliation/scan 非 admin 必 403(写候选也要 admin,fail-closed)。"""
    user, headers = auth_user_and_headers
    # 不设 user.is_admin → 默认非管理员
    resp = client.post("/api/v1/admin/knowledge/reconciliation/scan", headers=headers)
    assert resp.status_code == 403


def test_queue_lists_and_filters(db):
    _doc(db, "dd:hp", doc_type="entity", origin=DOWN, entity_id="e:hp", content_hash="h1")
    _doc(db, "kb:hp", doc_type="entity", origin=KBASE, review_status="draft", entity_id="e:hp", content_hash="h1")
    _doc(db, "dd:c", doc_type="claim", origin=DOWN, content_hash="h2", title="claimX")
    _doc(db, "kb:c", doc_type="claim", origin=KBASE, review_status="draft", content_hash="h2", title="claimX")
    detect_reconciliation_candidates(db)

    all_open = list_reconciliation_candidates(db, status="open")
    assert all_open["total"] == 2
    only_entity = list_reconciliation_candidates(db, status="open", kind="entity_align")
    assert only_entity["total"] == 1
    assert only_entity["candidates"][0]["kind"] == "entity_align"
    only_dup = list_reconciliation_candidates(db, status="open", relation_tag="duplicate")
    # 两对都是 content_hash 相同 → 都 duplicate
    assert only_dup["total"] == 2
