"""System KB V2 邻域图读取(admin-only,种子 + hops≤2 有界邻域)。

「融合可见」图视图的数据源:从一个种子文档出发 BFS over KBEdge,返回有界邻域的 nodes + edges,
供 admin 页 SVG 图渲染(按 entity_type 上色、按 origin 描边)。借 kg_service.expand_neighborhood 的
hop/方向语义,但**读 System KB 表(KBDocument/KBEdge),不是 user-scoped HealthEntity**。

⚠️ **治理隔离(设计里最大风险,必须钉死)**:本模块**故意不套 reviewed serving 门**
(`_serving_document_filters`)—— reviewer 必须能看见 draft/needs_review 节点才审得动。因此本函数
**只允许 admin 读路径调用,绝不能被 lookup_for_twin / knowledge_librarian / search_knowledge 调用**
(那三条保留 reviewed 门,只给 Twin/Orchestrator 喂 reviewed)。隔离测试钉死:本函数返回某 draft 节点,
而 lookup_for_twin 对同一 doc_id 仍返回空。只读 kb_documents(已转换面),不碰原始笔记。
"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument, KBEdge

MAX_HOPS = 2
DEFAULT_MAX_NODES = 120


def _node_dict(d: KBDocument, hop: int) -> Dict[str, Any]:
    meta = d.metadata_json or {}
    return {
        "doc_id": d.doc_id,
        "doc_type": d.doc_type,
        "entity_type": d.entity_type,
        "title": d.title,
        "review_status": meta.get("review_status"),
        "origin": meta.get("origin"),
        "confidence": d.confidence,
        "hop": hop,
    }


def _edge_dict(e: KBEdge) -> Dict[str, Any]:
    meta = e.metadata_json or {}
    return {
        "src": e.src_doc_id,
        "dst": e.dst_doc_id,
        "relation": e.relation,
        "confidence": e.confidence,
        "origin": meta.get("origin"),
    }


def admin_expand_kb_neighborhood(
    db: Session, seed_doc_id: str, *, hops: int = 2, max_nodes: int = DEFAULT_MAX_NODES
) -> Dict[str, Any]:
    """种子 + hops≤2 有界邻域(BFS over KBEdge,双向)。**admin-only,不套 serving 门(见模块注释)。**

    truncated=True 表示节点超 max_nodes 被截断。not_found=True 表示种子不存在。
    """
    hops = max(1, min(int(hops or MAX_HOPS), MAX_HOPS))
    max_nodes = max(1, int(max_nodes or DEFAULT_MAX_NODES))

    seed = db.query(KBDocument).filter(KBDocument.doc_id == seed_doc_id).first()
    if seed is None:
        return {"seed": seed_doc_id, "nodes": [], "edges": [], "truncated": False, "not_found": True}

    node_ids = {seed_doc_id}
    hop_of: Dict[str, int] = {seed_doc_id: 0}
    frontier = {seed_doc_id}
    edges_by_key: Dict[tuple, KBEdge] = {}
    truncated = False

    for hop in range(1, hops + 1):
        if not frontier:
            break
        touching = (
            db.query(KBEdge)
            .filter(or_(KBEdge.src_doc_id.in_(frontier), KBEdge.dst_doc_id.in_(frontier)))
            .all()
        )
        next_frontier: set[str] = set()
        for e in touching:
            edges_by_key[(e.src_doc_id, e.dst_doc_id, e.relation)] = e
            for nid in (e.src_doc_id, e.dst_doc_id):
                if nid in node_ids:
                    continue
                if len(node_ids) >= max_nodes:
                    truncated = True
                    continue
                node_ids.add(nid)
                hop_of[nid] = hop
                next_frontier.add(nid)
        frontier = next_frontier

    # 加载节点文档 —— **无 serving 门**(reviewer 要看 draft);仅 admin 读路径可达。
    docs = db.query(KBDocument).filter(KBDocument.doc_id.in_(node_ids)).all()
    nodes: List[Dict[str, Any]] = [_node_dict(d, hop_of.get(d.doc_id, 0)) for d in docs]

    # 只保留两端都在邻域内的边(截断后可能有悬边)
    edges: List[Dict[str, Any]] = [
        _edge_dict(e)
        for (s, d, _r), e in edges_by_key.items()
        if s in node_ids and d in node_ids
    ]

    return {
        "seed": seed_doc_id,
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
        "node_count": len(nodes),
        "hops": hops,
    }
