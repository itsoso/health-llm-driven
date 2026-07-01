"""System KB V2 覆盖矩阵 + **权威校验 eval**(纯读,零 mutation)。

「融合可见」第一屏的数据:entity_type × origin 覆盖矩阵 —— 一眼看 dedao-kbase 补了哪块、
和 down-dedao 哪里重叠。同时**自校验**:不信自己算的数,独立重算总数交叉核对,报出跨源重复候选,
让「863 文档」这个数诚实(不被隐藏的跨源重复撑虚)。

准确性不变量(嵌在返回的 `validation` 里,可断言、可上看板):
- **count 不变量**:各格 doc_count 之和 == 独立 `count(*)`(非归档)→ 无双计、无静默丢。
- reviewed_count ≤ doc_count(每格)。
- origin / entity_type **动态**(自由串,绝不写死列;NULL → 'unknown' 桶,不丢文档)。

跨源重复检测(P0 能权威判的子集 —— honest scope):
- `content_hash` 跨 origin 撞 = **确定重复**(同内容)。
- `entity_id` 跨 origin 撞 = 同实体两 pipeline。
- (entity_type, 归一 title) 跨 origin 撞 = 疑似重复。
- **别名级重复(Hp / 幽门螺杆菌,不同 title+entity_id)P0 检测不到 → 那是 Phase B 实体对齐的活**,
  本 eval 明确不假装覆盖它(`alias_level_dups_out_of_scope=True`)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_service import _normalize_knowledge_text

UNKNOWN = "unknown"


def _norm_title(title: Any) -> str:
    return _normalize_knowledge_text(title or "")


def _cross_source_groups(
    bucket: Dict[Any, List[Tuple[str, str, str]]], signal: str
) -> List[Dict[str, Any]]:
    """bucket: key -> [(origin, doc_id, entity_type)]。返回跨 ≥2 个不同 origin 的组(=跨源重复候选)。"""
    out: List[Dict[str, Any]] = []
    for key, entries in bucket.items():
        origins = sorted({o for (o, _, _) in entries if o != UNKNOWN})
        if len(origins) < 2:
            continue  # 单源(或全 unknown)不算跨源重复
        out.append({
            "signal": signal,
            "key": str(key),
            "entity_type": entries[0][2],
            "origins": origins,
            "doc_ids": sorted({d for (_, d, _) in entries}),
        })
    return out


def build_coverage_matrix(db: Session) -> Dict[str, Any]:
    """entity_type × origin 覆盖矩阵 + 自校验 + 跨源重复候选。纯读、非归档文档。"""
    docs = db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).all()

    cells: Dict[Tuple[str, str], Dict[str, Any]] = {}
    origins: set[str] = set()
    entity_types: set[str] = set()
    total = 0
    total_reviewed = 0
    by_hash: Dict[str, List[Tuple[str, str, str]]] = {}
    by_entity: Dict[str, List[Tuple[str, str, str]]] = {}
    by_title: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = {}

    for d in docs:
        total += 1
        meta = d.metadata_json or {}
        origin = str(meta.get("origin") or UNKNOWN)
        etype = str(d.entity_type or UNKNOWN)
        reviewed = meta.get("review_status") == "reviewed"
        origins.add(origin)
        entity_types.add(etype)

        cell = cells.setdefault(
            (etype, origin),
            {"doc_count": 0, "reviewed_count": 0, "conf_sum": 0.0, "conf_n": 0},
        )
        cell["doc_count"] += 1
        if reviewed:
            cell["reviewed_count"] += 1
            total_reviewed += 1
        if d.confidence is not None:
            cell["conf_sum"] += float(d.confidence)
            cell["conf_n"] += 1

        entry = (origin, d.doc_id, etype)
        if d.content_hash:
            by_hash.setdefault(d.content_hash, []).append(entry)
        if d.entity_id:
            by_entity.setdefault(d.entity_id, []).append(entry)
        by_title.setdefault((etype, _norm_title(d.title)), []).append(entry)

    matrix = [
        {
            "entity_type": et,
            "origin": og,
            "doc_count": c["doc_count"],
            "reviewed_count": c["reviewed_count"],
            "avg_confidence": round(c["conf_sum"] / c["conf_n"], 3) if c["conf_n"] else None,
        }
        for (et, og), c in sorted(cells.items())
    ]

    dups = (
        _cross_source_groups(by_hash, "content_hash")
        + _cross_source_groups(by_entity, "entity_id")
        + _cross_source_groups(
            {k: v for k, v in by_title.items() if k[1]}, "normalized_title"
        )
    )

    # ── 权威校验:独立重算总数交叉核对(不信矩阵自己的和) ──
    matrix_total = sum(cell["doc_count"] for cell in matrix)
    independent_total = (
        db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).count()
    )
    validation = {
        "count_invariant_ok": matrix_total == total == independent_total,
        "matrix_total": matrix_total,
        "actual_total": total,
        "independent_total": independent_total,
        "reviewed_le_doc_ok": all(
            cell["reviewed_count"] <= cell["doc_count"] for cell in matrix
        ),
        "cross_source_dup_count": len(dups),
        "alias_level_dups_out_of_scope": True,  # Hp/幽门螺杆菌 类别名重复 → Phase B 实体对齐
    }

    return {
        "matrix": matrix,
        "origins": sorted(origins),
        "entity_types": sorted(entity_types),
        "totals": {"doc_count": total, "reviewed_count": total_reviewed},
        "cross_source_duplicates": dups,
        "validation": validation,
    }
