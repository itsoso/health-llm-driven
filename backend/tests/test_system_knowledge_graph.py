"""KB 邻域图(P2):BFS 有界邻域 + **治理隔离**(admin 图见 draft,但 serving 门仍排除 draft 不漏进 runtime)。"""
from app.models.system_knowledge import KBDocument, KBEdge
from app.services.system_knowledge_graph import admin_expand_kb_neighborhood


def _doc(db, doc_id, *, entity_type="condition", review_status="reviewed",
         origin="down-dedao-llm-wiki", title="x"):
    db.add(KBDocument(
        doc_id=doc_id, doc_type="claim", entity_type=entity_type, title=title,
        is_archived=False, metadata_json={"review_status": review_status, "origin": origin},
    ))
    db.commit()


def _edge(db, src, dst, relation="relates_to"):
    db.add(KBEdge(src_doc_id=src, dst_doc_id=dst, relation=relation))
    db.commit()


def _ids(res):
    return {n["doc_id"] for n in res["nodes"]}


def test_bfs_seed_and_two_hops(db):
    for i in range(4):
        _doc(db, f"n{i}")
    _edge(db, "n0", "n1")   # hop1
    _edge(db, "n1", "n2")   # hop2
    _edge(db, "n2", "n3")   # hop3 — 不该进(hops=2)
    res = admin_expand_kb_neighborhood(db, "n0", hops=2)
    assert _ids(res) == {"n0", "n1", "n2"}
    hop = {n["doc_id"]: n["hop"] for n in res["nodes"]}
    assert hop["n0"] == 0 and hop["n1"] == 1 and hop["n2"] == 2


def test_bidirectional(db):
    _doc(db, "a"); _doc(db, "b")
    _edge(db, "b", "a")  # 指向 seed 的入边也要遍历到
    res = admin_expand_kb_neighborhood(db, "a", hops=1)
    assert _ids(res) == {"a", "b"}


def test_hops_capped_at_2(db):
    _doc(db, "s")
    res = admin_expand_kb_neighborhood(db, "s", hops=9)
    assert res["hops"] == 2


def test_max_nodes_truncation(db):
    _doc(db, "hub")
    for i in range(10):
        _doc(db, f"leaf{i}")
        _edge(db, "hub", f"leaf{i}")
    res = admin_expand_kb_neighborhood(db, "hub", hops=1, max_nodes=4)
    assert res["truncated"] is True
    assert res["node_count"] <= 4


def test_edges_only_between_collected_nodes(db):
    _doc(db, "hub")
    for i in range(6):
        _doc(db, f"x{i}")
        _edge(db, "hub", f"x{i}")
    res = admin_expand_kb_neighborhood(db, "hub", hops=1, max_nodes=3)
    ids = _ids(res)
    for e in res["edges"]:
        assert e["src"] in ids and e["dst"] in ids  # 无悬边


def test_seed_not_found(db):
    res = admin_expand_kb_neighborhood(db, "does_not_exist")
    assert res["not_found"] is True and res["nodes"] == []


def test_isolation_admin_sees_draft_but_serving_gate_excludes_it(db):
    """治理隔离(设计最大风险):admin 图能看见 draft 节点(reviewer 要审),
    但 lookup_for_twin/search 用的 serving 门仍排除 draft → 绝不漏进 Twin/Orchestrator。"""
    from app.services.system_knowledge_service import _serving_document_filters

    _doc(db, "seed", review_status="reviewed")
    _doc(db, "draft_neighbor", review_status="draft")
    _edge(db, "seed", "draft_neighbor")

    res = admin_expand_kb_neighborhood(db, "seed", hops=1)
    # admin 图看得见 draft(否则没法审)
    assert "draft_neighbor" in _ids(res)
    draft_node = next(n for n in res["nodes"] if n["doc_id"] == "draft_neighbor")
    assert draft_node["review_status"] == "draft"

    # 但 serving 门(runtime 那条)仍排除 draft —— 隔离成立,admin bypass 不改 runtime 服务内容
    served = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id == "draft_neighbor", *_serving_document_filters())
        .first()
    )
    assert served is None
    # 对照:reviewed 种子能过 serving 门
    served_seed = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id == "seed", *_serving_document_filters())
        .first()
    )
    assert served_seed is not None
