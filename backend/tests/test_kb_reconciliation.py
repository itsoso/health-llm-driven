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
    aliases=None,  # None=不写 aliases 键;list=正常;非 list(如 str)=脏数据故意触发 fail-loud
):
    meta = {"origin": origin, "review_status": review_status}
    if aliases is not None:
        meta["aliases"] = aliases
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
            metadata_json=meta,
        )
    )
    db.commit()


def _edge(db, src, dst, relation="has_claim"):
    from app.models.system_knowledge import KBEdge

    db.add(KBEdge(src_doc_id=src, dst_doc_id=dst, relation=relation))
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


# ─────────────────── 语义对齐信号(edge_neighborhood + alias_overlap)───────────────────

def test_alias_overlap_surfaces_crosssource_alias_old_detector_missed(db):
    """别名级跨源重复(Hp vs 幽门螺杆菌):不同 entity_id + 不同 title + 无同 hash,
    旧结构 detector 结构上抓不到;alias_overlap 靠共享 title/alias token 捞出来。"""
    from app.services.kb_reconciliation import _norm_title

    _doc(db, "dd:hp+", doc_type="entity", entity_type="condition", entity_id="e:hp-pos",
         origin=DOWN, review_status="reviewed", content_hash="hA", title="幽门螺杆菌阳性",
         aliases=["幽门螺杆菌", "pylori", "hp阳性"])
    _doc(db, "kb:hp?", doc_type="entity", entity_type="bacterium", entity_id="e:hp-unknown",
         origin=KBASE, review_status="draft", content_hash="hB", title="Hp感染",
         aliases=["幽门螺杆菌", "pylori", "hp感染"])
    # 前置证明 gap:结构键全 miss
    a = db.query(KBDocument).filter(KBDocument.doc_id == "dd:hp+").first()
    b = db.query(KBDocument).filter(KBDocument.doc_id == "kb:hp?").first()
    assert a.content_hash != b.content_hash
    assert a.entity_id != b.entity_id
    assert _norm_title(a.title) != _norm_title(b.title)

    res = detect_reconciliation_candidates(db)
    assert res["created"] == 1
    c = db.query(KBReconciliationCandidate).first()
    assert c.relation_tag is None  # 语义信号永不标 duplicate
    assert c.kind == "entity_align"
    assert "alias_overlap" in c.signals["detectors"]
    assert c.signals["alias_overlap"]["shared_tokens"]  # reviewer 能看到为什么
    assert c.canonical_hint == "dd:hp+"  # D1:down-dedao reviewed 侧
    assert c.status == "open"


def test_edge_neighborhood_surfaces_shared_neighbor_alias(db):
    """共享 KBEdge 邻域:两跨源 entity(不同 entity_id/title/hash,entity_type 甚至不同)
    各连同样 3 个 claim 邻居 → edge_neighborhood 捞出别名候选。"""
    _doc(db, "dd:hp+", doc_type="entity", entity_type="bacterium", entity_id="e:hp-pos",
         origin=DOWN, review_status="reviewed", content_hash="hA", title="幽门螺杆菌阳性")
    _doc(db, "kb:hp?", doc_type="entity", entity_type="condition", entity_id="e:hp-unknown",
         origin=KBASE, review_status="draft", content_hash="hB", title="Hp感染状况")
    for i in range(3):
        _doc(db, f"c{i}", doc_type="claim", title=f"claim{i}", content_hash=f"hc{i}")
        _edge(db, "dd:hp+", f"c{i}", relation="mentions")
        _edge(db, "kb:hp?", f"c{i}", relation="mentions")
    res = detect_reconciliation_candidates(db)
    # 两 entity 共享 3 邻居 → 恰 1 候选(claim 邻居非 entity,不自成对)
    align = [r for r in db.query(KBReconciliationCandidate).all() if r.kind == "entity_align"]
    assert len(align) == 1
    c = align[0]
    assert "edge_neighborhood" in c.signals["detectors"]
    assert c.signals["edge_neighborhood"]["shared_count"] >= 3
    assert c.relation_tag is None


def test_single_hub_neighbor_below_threshold_no_candidate(db):
    """负例/防泛滥:两跨源 entity 只共享 1 个邻居(< _MIN_SHARED_NEIGHBORS)、无 alias 重叠 → 零候选。"""
    _doc(db, "dd:x", doc_type="entity", entity_type="condition", entity_id="e:x",
         origin=DOWN, content_hash="hX", title="实体X独特名")
    _doc(db, "kb:y", doc_type="entity", entity_type="condition", entity_id="e:y",
         origin=KBASE, review_status="draft", content_hash="hY", title="实体Y另名")
    _doc(db, "hub", doc_type="claim", title="公共hub", content_hash="hh")
    _edge(db, "dd:x", "hub", relation="mentions")
    _edge(db, "kb:y", "hub", relation="mentions")
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 0  # 单个共享 hub 不足以成对


def test_semantic_signal_zero_serving_mutation_incl_edges(db):
    """最高价值:语义扫描后 kb_documents **和 kb_edges** 逐行不变(读边不改边)。"""
    from app.models.system_knowledge import KBEdge

    _doc(db, "dd:hp+", doc_type="entity", entity_id="e:hp-pos", origin=DOWN,
         review_status="reviewed", content_hash="hA", title="幽门螺杆菌阳性",
         aliases=["幽门螺杆菌", "pylori"])
    _doc(db, "kb:hp?", doc_type="entity", entity_id="e:hp-unknown", origin=KBASE,
         review_status="draft", content_hash="hB", title="Hp感染", aliases=["幽门螺杆菌", "pylori"])
    _doc(db, "c0", doc_type="claim", title="c0", content_hash="hc0")
    _edge(db, "dd:hp+", "c0", relation="mentions")

    docs_before = {d.doc_id: (d.content_hash, d.is_archived, dict(d.metadata_json or {}))
                   for d in db.query(KBDocument).all()}
    edges_before = sorted((e.src_doc_id, e.dst_doc_id, e.relation) for e in db.query(KBEdge).all())

    detect_reconciliation_candidates(db)

    docs_after = {d.doc_id: (d.content_hash, d.is_archived, dict(d.metadata_json or {}))
                  for d in db.query(KBDocument).all()}
    edges_after = sorted((e.src_doc_id, e.dst_doc_id, e.relation) for e in db.query(KBEdge).all())
    assert docs_after == docs_before  # 无 archive、无 merged_into/aliases 改写
    assert edges_after == edges_before  # 无加边/删边/重指


def test_semantic_signal_idempotent(db):
    _doc(db, "dd:hp+", doc_type="entity", entity_id="e:hp-pos", origin=DOWN,
         content_hash="hA", title="幽门螺杆菌阳性", aliases=["幽门螺杆菌", "pylori"])
    _doc(db, "kb:hp?", doc_type="entity", entity_id="e:hp-unknown", origin=KBASE,
         review_status="draft", content_hash="hB", title="Hp感染", aliases=["幽门螺杆菌", "pylori"])
    first = detect_reconciliation_candidates(db)
    assert first["created"] == 1
    second = detect_reconciliation_candidates(db)
    assert second["created"] == 0
    assert db.query(KBReconciliationCandidate).count() == 1


def test_semantic_signal_same_origin_not_surfaced(db):
    """同 origin 两 entity 即便共享邻居 + alias 也不成跨源候选。"""
    _doc(db, "kb:a", doc_type="entity", entity_id="e:a", origin=KBASE, review_status="draft",
         content_hash="hA", title="实体A", aliases=["幽门螺杆菌", "pylori"])
    _doc(db, "kb:b", doc_type="entity", entity_id="e:b", origin=KBASE, review_status="draft",
         content_hash="hB", title="实体B", aliases=["幽门螺杆菌", "pylori"])
    res = detect_reconciliation_candidates(db)
    assert res["created"] == 0


def test_super_hub_neighbor_is_bounded_and_flagged(monkeypatch):
    """边界/fail-loud:被极多 entity 触达的超级 hub token 不展开 O(m²),oversized_neighbor_tokens 暴露。"""
    import app.services.kb_reconciliation as m
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    monkeypatch.setattr(m, "_MAX_NEIGHBOR_FANOUT", 3)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    s = S()
    try:
        _doc(s, "hub", doc_type="claim", title="超级hub", content_hash="hh")
        for i in range(8):  # 8 个 entity 都连同一 hub → hub token 的 posting list=8 > 3
            origin = DOWN if i % 2 == 0 else KBASE
            _doc(s, f"e{i}", doc_type="entity", entity_id=f"e:{i}", origin=origin,
                 review_status="reviewed" if origin == DOWN else "draft",
                 content_hash=f"h{i}", title=f"实体{i}独特")
            _edge(s, f"e{i}", "hub", relation="mentions")
        res = detect_reconciliation_candidates(s)
        assert res["oversized_neighbor_tokens"] >= 1  # 超级 hub 被跳且计数
    finally:
        s.close()


import pytest


@pytest.mark.parametrize("bad_aliases", ["不是列表是字符串", {"k": "v"}, 42])
def test_malformed_aliases_counted_not_swallowed(db, bad_aliases):
    """脏 aliases(非 list:str/dict/int 都算)fail-loud 计数,不静默吞、不抛。"""
    _doc(db, "dd:bad", doc_type="entity", entity_id="e:bad", origin=DOWN,
         content_hash="hA", title="坏别名实体", aliases=bad_aliases)
    _doc(db, "kb:ok", doc_type="entity", entity_id="e:ok", origin=KBASE, review_status="draft",
         content_hash="hB", title="正常实体")
    res = detect_reconciliation_candidates(db)  # 不抛
    assert res["malformed_alias_docs"] >= 1
