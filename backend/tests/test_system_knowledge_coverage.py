"""KB 覆盖矩阵 + 权威校验 eval(P0):准确(count 不变量)、不重复(跨源重复检测)、动态 origin。"""
from app.models.system_knowledge import KBDocument
from app.services.system_knowledge_coverage import build_coverage_matrix


def _doc(db, doc_id, *, entity_type="condition", origin="down-dedao-llm-wiki",
         review_status="reviewed", title="幽门螺杆菌", entity_id=None,
         content_hash=None, confidence=0.8, archived=False):
    db.add(KBDocument(
        doc_id=doc_id, doc_type="claim", entity_type=entity_type, entity_id=entity_id,
        title=title, confidence=confidence, content_hash=content_hash, is_archived=archived,
        metadata_json={"origin": origin, "review_status": review_status},
    ))
    db.commit()


def _cell(res, et, og):
    return next((c for c in res["matrix"] if c["entity_type"] == et and c["origin"] == og), None)


def test_matrix_shape_and_dynamic_origins(db):
    _doc(db, "d1", entity_type="condition", origin="down-dedao-llm-wiki")
    _doc(db, "d2", entity_type="condition", origin="dedao-kbase-export", review_status="draft")
    _doc(db, "d3", entity_type="supplement", origin="owner_curated")
    res = build_coverage_matrix(db)
    # origin 动态(3 个源都在,没写死)
    assert set(res["origins"]) == {"down-dedao-llm-wiki", "dedao-kbase-export", "owner_curated"}
    assert set(res["entity_types"]) == {"condition", "supplement"}
    # condition 两源都非空 = 重叠区
    assert _cell(res, "condition", "down-dedao-llm-wiki")["doc_count"] == 1
    assert _cell(res, "condition", "dedao-kbase-export")["doc_count"] == 1


def test_count_invariant_authoritative(db):
    for i in range(7):
        _doc(db, f"d{i}", origin="down-dedao-llm-wiki" if i % 2 else "dedao-kbase-export")
    res = build_coverage_matrix(db)
    v = res["validation"]
    # 三路独立算的总数一致 = 无双计、无静默丢
    assert v["count_invariant_ok"] is True
    assert v["matrix_total"] == v["actual_total"] == v["independent_total"] == 7
    assert res["totals"]["doc_count"] == 7


def test_reviewed_le_doc(db):
    _doc(db, "r1", origin="X", review_status="reviewed")
    _doc(db, "r2", origin="X", review_status="draft")
    res = build_coverage_matrix(db)
    c = _cell(res, "condition", "X")
    assert c["reviewed_count"] == 1 and c["doc_count"] == 2
    assert res["validation"]["reviewed_le_doc_ok"] is True


def test_null_origin_to_unknown_not_dropped(db):
    # 无 origin 的文档不能被静默丢 → 进 'unknown' 桶,仍计入总数
    db.add(KBDocument(doc_id="no_origin", doc_type="claim", entity_type="condition",
                      title="x", is_archived=False, metadata_json={}))
    db.commit()
    res = build_coverage_matrix(db)
    assert "unknown" in res["origins"]
    assert _cell(res, "condition", "unknown")["doc_count"] == 1
    assert res["validation"]["count_invariant_ok"] is True  # 没丢


def test_cross_source_dup_by_content_hash(db):
    # 同 content_hash + 不同 origin = 确定跨源重复(让「总数」诚实)
    _doc(db, "h1", origin="down-dedao-llm-wiki", content_hash="ABC123")
    _doc(db, "h2", origin="dedao-kbase-export", content_hash="ABC123")
    res = build_coverage_matrix(db)
    dups = [d for d in res["cross_source_duplicates"] if d["signal"] == "content_hash"]
    assert len(dups) == 1
    assert set(dups[0]["origins"]) == {"down-dedao-llm-wiki", "dedao-kbase-export"}
    assert set(dups[0]["doc_ids"]) == {"h1", "h2"}
    assert res["validation"]["cross_source_dup_count"] >= 1


def test_cross_source_dup_by_entity_id_and_title(db):
    _doc(db, "e1", origin="down-dedao-llm-wiki", entity_id="ent:hp", title="幽门螺杆菌")
    _doc(db, "e2", origin="dedao-kbase-export", entity_id="ent:hp", title="幽门螺杆菌")
    res = build_coverage_matrix(db)
    sigs = {d["signal"] for d in res["cross_source_duplicates"]}
    assert "entity_id" in sigs and "normalized_title" in sigs


def test_same_origin_dup_not_cross_source(db):
    # 同 content_hash 但同 origin → 不是跨源重复(不误报)
    _doc(db, "s1", origin="down-dedao-llm-wiki", content_hash="SAME")
    _doc(db, "s2", origin="down-dedao-llm-wiki", content_hash="SAME")
    res = build_coverage_matrix(db)
    assert res["validation"]["cross_source_dup_count"] == 0


def test_archived_excluded(db):
    _doc(db, "a1", origin="X")
    _doc(db, "a2", origin="X", archived=True)
    res = build_coverage_matrix(db)
    assert res["totals"]["doc_count"] == 1  # 归档不计


def test_alias_dups_honestly_out_of_scope(db):
    # Hp vs 幽门螺杆菌(不同 title + 不同 entity_id)—— P0 检测不到,eval 诚实声明留给 Phase B
    _doc(db, "hp1", origin="down-dedao-llm-wiki", entity_id="ent:hp", title="幽门螺杆菌")
    _doc(db, "hp2", origin="dedao-kbase-export", entity_id="ent:h-pylori", title="Hp")
    res = build_coverage_matrix(db)
    assert res["validation"]["alias_level_dups_out_of_scope"] is True
    # 别名对不被 P0 当重复(诚实:不假装覆盖)
    assert not any(set(d["doc_ids"]) == {"hp1", "hp2"} for d in res["cross_source_duplicates"])
