from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument, KBDocumentVector, KBEdge
from app.services import system_knowledge_service
from app.services.system_knowledge_service import reindex_knowledge_documents, search_knowledge


def _seed_vector_knowledge(db):
    entity = KBDocument(
        doc_id="entity:gene:MTHFR",
        doc_type="entity",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR",
        summary="MTHFR 参与一碳代谢和叶酸转化。",
        body="MTHFR C677T 会影响叶酸向 5-MTHF 的转化效率。",
        confidence=0.88,
        evidence_level="B",
        sources=["dedao:qiuzilong-genetics-07"],
        last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        decay_rate="slow",
        metadata_json={"review_status": "reviewed"},
    )
    claim = KBDocument(
        doc_id="claim:c_mthfr_c677t_hcy_folate_boundary",
        doc_type="claim",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR C677T 与叶酸转化边界",
        summary="C677T CT/TT 用户可优先关注同型半胱氨酸、B12 与活性叶酸。",
        body="该 claim 只支持健康管理提示，不用于诊断或治疗。",
        confidence=0.82,
        evidence_level="B",
        applies_when=[
            "twin.genetics.MTHFR_C677T in ['CT', 'TT']",
            "twin.labs.homocysteine_umol_l >= 15",
        ],
        recommends_lookup=["entity:supplement:5-MTHF", "entity:biomarker:Hcy"],
        sources=["dedao:qiuzilong-genetics-07", "pubmed:19033271"],
        last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        decay_rate="normal",
        metadata_json={"review_status": "reviewed", "domain": "nutrition"},
    )
    draft = KBDocument(
        doc_id="claim:c_mthfr_draft_vector_should_not_serve",
        doc_type="claim",
        entity_type="gene",
        entity_id="MTHFR",
        title="Draft homocysteine claim",
        summary="homocysteine draft result should never enter serving vector results.",
        confidence=0.99,
        evidence_level="B",
        metadata_json={"review_status": "draft"},
    )
    db.add_all([entity, claim, draft])
    db.flush()
    db.add(
        KBEdge(
            src_doc_id=entity.doc_id,
            dst_doc_id=claim.doc_id,
            relation="has_claim",
            confidence=0.9,
            source_claim_id=claim.doc_id,
        )
    )
    db.commit()


def test_search_vector_channel_uses_index_rows_not_alias_fallback(db):
    _seed_vector_knowledge(db)

    before_index = search_knowledge(db, "methylfolate", limit=5)

    assert before_index["retrieval_plan"]["vector_backend"] == "sparse_term_cosine_v1"
    assert before_index["results"] == []

    reindex_result = reindex_knowledge_documents(db, actor="test")

    assert reindex_result["documents"] == 3
    vector = db.query(KBDocumentVector).filter(
        KBDocumentVector.doc_id == "claim:c_mthfr_c677t_hcy_folate_boundary"
    ).one()
    assert vector.embedding_model == "sparse_term_cosine_v1"
    assert vector.magnitude > 0
    assert "活性叶酸" in vector.vector_json

    after_index = search_knowledge(db, "methylfolate", limit=5)
    result_ids = [item["document"]["doc_id"] for item in after_index["results"]]
    claim_result = next(
        item
        for item in after_index["results"]
        if item["document"]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"
    )

    assert "claim:c_mthfr_c677t_hcy_folate_boundary" in result_ids
    assert "claim:c_mthfr_draft_vector_should_not_serve" not in result_ids
    assert after_index["retrieval_plan"]["vector_backend"] == "sparse_term_cosine_v1"
    assert "vector" in claim_result["retrieval"]["channels"]
    assert claim_result["retrieval"]["vector_score"] > 0


def test_search_vector_channel_prefers_pgvector_backend_when_available(db, monkeypatch):
    _seed_vector_knowledge(db)

    def fake_pgvector_backend(_db):
        return "pgvector:text-embedding-3-small"

    def fake_pgvector_rank(_db, documents_by_id, query, *, limit):
        assert query == "semantic-only-query"
        claim = documents_by_id["claim:c_mthfr_c677t_hcy_folate_boundary"]
        return [(0.93, claim)]

    monkeypatch.setattr(system_knowledge_service, "_pgvector_backend_for_session", fake_pgvector_backend, raising=False)
    monkeypatch.setattr(system_knowledge_service, "_rank_pgvector_documents", fake_pgvector_rank, raising=False)

    payload = search_knowledge(db, "semantic-only-query", limit=5)
    claim_result = next(
        item
        for item in payload["results"]
        if item["document"]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"
    )

    assert payload["retrieval_plan"]["vector_backend"] == "pgvector:text-embedding-3-small"
    assert "vector" in claim_result["retrieval"]["channels"]
    assert claim_result["retrieval"]["vector_score"] > 0
