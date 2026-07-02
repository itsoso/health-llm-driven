"""KB 邻域图(P2):BFS 有界邻域 + **治理隔离**(admin 图见 draft,但 serving 门仍排除 draft 不漏进 runtime)。"""
import re
from pathlib import Path

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


def test_no_runtime_module_imports_the_graph_module():
    """治理隔离机械护栏(fail-loud):`system_knowledge_graph` 故意不套 reviewed serving 门,
    只允许 admin 读路径调用。任何 runtime 面(twin / agents / orchestrator / tasks /
    运行时 KB service)一旦 import 它,就等于把未审 draft 内容接进了用户面健康建议 —— 违反
    reviewed-only-serving 不变量。这里把「约定」升成 CI 强制:扫描这些目录,发现引用即红。

    允许引用的白名单:api/system_knowledge.py(admin /graph 端点唯一合法入口)、
    services/system_knowledge_graph.py 自身、以及 tests/。"""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    guarded = [
        app_dir / "twin",
        app_dir / "agents",
        app_dir / "orchestrator",
        app_dir / "tasks",
        app_dir / "services" / "system_knowledge_service.py",
    ]
    pattern = re.compile(r"system_knowledge_graph|admin_expand_kb_neighborhood")
    offenders: list[str] = []
    for target in guarded:
        py_files = [target] if target.is_file() else sorted(target.rglob("*.py"))
        for f in py_files:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{f.relative_to(app_dir.parent)}:{i}: {line.strip()}")
    assert not offenders, (
        "runtime 模块引用了 admin-only 的 system_knowledge_graph(会把未审 draft 漏进用户面):\n"
        + "\n".join(offenders)
    )


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


def test_admin_get_document_returns_full_provenance(db):
    """admin 单文档读:含 draft/archived,serialize_document 全量含 metadata.provenance_lineage。"""
    from app.services.system_knowledge_graph import admin_get_document

    db.add(KBDocument(
        doc_id="c:hp:merged", doc_type="entity", entity_type="condition", title="幽门螺杆菌",
        is_archived=False,
        metadata_json={
            "origin": "down-dedao-llm-wiki", "review_status": "reviewed",
            "license_scope": "internal_transformed_claims",
            "aliases": ["Hp", "pylori"],
            "provenance_lineage": [
                {"folded_doc_id": "kb:hp", "origin": "dedao-kbase-export",
                 "license_scope": "internal_transformed_claims", "folded_by": "admin:1"}
            ],
        },
    ))
    db.commit()
    doc = admin_get_document(db, "c:hp:merged")
    assert doc is not None
    assert doc["metadata"]["origin"] == "down-dedao-llm-wiki"
    assert doc["metadata"]["provenance_lineage"][0]["folded_doc_id"] == "kb:hp"
    assert admin_get_document(db, "does_not_exist") is None


def test_admin_get_document_under_runtime_import_lint():
    """admin_get_document 与图同属 admin bypass 面 —— 已由 test_no_runtime_module_imports_the_graph_module
    覆盖(runtime 不 import system_knowledge_graph)。此处占位确认它在同模块。"""
    from app.services import system_knowledge_graph as g
    assert hasattr(g, "admin_get_document") and hasattr(g, "admin_expand_kb_neighborhood")
