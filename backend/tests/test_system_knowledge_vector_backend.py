from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
import sys

from app.config import settings
from app.models.system_knowledge import KBAudit, KBDocument, KBDocumentVector, KBEdge
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


def test_reindex_prepares_pgvector_table_before_sparse_document_updates(db, monkeypatch):
    _seed_vector_knowledge(db)
    calls = []

    def fake_ensure_pgvector_table(_db):
        calls.append("ensure_pgvector_table")
        return False

    def fake_upsert_document_vector(_db, doc_id, searchable, content_hash):
        calls.append(f"sparse:{doc_id}")

    monkeypatch.setattr(system_knowledge_service, "_ensure_pgvector_table", fake_ensure_pgvector_table)
    monkeypatch.setattr(system_knowledge_service, "_upsert_document_vector", fake_upsert_document_vector)

    result = reindex_knowledge_documents(db, actor="test")

    assert result["documents"] == 3
    assert calls[0] == "ensure_pgvector_table"
    assert any(call.startswith("sparse:") for call in calls[1:])


def test_pgvector_readiness_check_never_attempts_runtime_ddl(monkeypatch):
    class RuntimeSession:
        def get_bind(self):
            raise AssertionError("runtime readiness checks must not request a DDL connection")

    monkeypatch.setattr(settings, "system_kb_pgvector_enabled", True)
    monkeypatch.setattr(system_knowledge_service, "_is_postgres_session", lambda _db: True)
    monkeypatch.setattr(system_knowledge_service, "_pgvector_table_exists", lambda _db: True)

    assert system_knowledge_service._ensure_pgvector_table(RuntimeSession()) is True


def test_pgvector_table_is_owned_by_managed_migrations():
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "managed"
        / "20260722_120000_create_system_knowledge_embeddings.postgresql.sql"
    )

    sql = migration.read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE TABLE IF NOT EXISTS kb_document_embeddings" in sql
    assert "vector(1024)" in sql
    assert "ix_kb_document_embeddings_embedding_cosine" in sql


def test_system_kb_reindex_report_audits_pgvector_health(db, monkeypatch):
    _seed_vector_knowledge(db)

    def fake_pgvector_health(_db):
        return {
            "enabled": True,
            "postgres": True,
            "table_exists": True,
            "embedding_model": "text-embedding-v3",
            "embedding_rows": 3,
            "current_vector_backend": "pgvector:text-embedding-v3",
        }

    monkeypatch.setattr(system_knowledge_service, "get_system_kb_pgvector_health", fake_pgvector_health)

    report = system_knowledge_service.run_system_kb_reindex_report(db, actor="test")

    assert report["reindex"]["documents"] == 3
    assert report["reindex"]["dense_vectors"] == 0
    assert report["pgvector"]["embedding_rows"] == 3
    assert report["pgvector"]["current_vector_backend"] == "pgvector:text-embedding-v3"

    audit = db.query(KBAudit).filter(KBAudit.op == "system_kb_reindex_report").one()
    assert audit.actor == "test"
    assert audit.diff["reindex"]["documents"] == 3
    assert audit.diff["pgvector"]["embedding_rows"] == 3


def test_system_kb_embeddings_use_dedicated_provider_settings(monkeypatch):
    captured = {}

    class FakeEmbeddings:
        def create(self, *, model, input):
            captured["model"] = model
            captured["input"] = input
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[0.1, 0.2, 0.3])
                    for _ in input
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(settings, "system_kb_embedding_api_key", "system-kb-key")
    monkeypatch.setattr(settings, "system_kb_embedding_base_url", "https://embedding.example/v1")
    monkeypatch.setattr(settings, "system_kb_embedding_model", "text-embedding-v3")

    embeddings = system_knowledge_service._embed_system_kb_texts(["hello"])

    assert embeddings == [[0.1, 0.2, 0.3]]
    assert captured["client_kwargs"] == {
        "api_key": "system-kb-key",
        "base_url": "https://embedding.example/v1",
    }
    assert captured["model"] == "text-embedding-v3"


def test_system_kb_embeddings_honor_configured_batch_size(monkeypatch):
    calls = []

    class FakeEmbeddings:
        def create(self, *, model, input):
            calls.append(list(input))
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[float(index)])
                    for index, _ in enumerate(input)
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(settings, "system_kb_embedding_api_key", "system-kb-key")
    monkeypatch.setattr(settings, "system_kb_embedding_base_url", "https://embedding.example/v1")
    monkeypatch.setattr(settings, "system_kb_embedding_batch_size", 2)

    embeddings = system_knowledge_service._embed_system_kb_texts(["a", "b", "c", "d", "e"])

    assert embeddings == [[0.0], [1.0], [0.0], [1.0], [0.0]]
    assert calls == [["a", "b"], ["c", "d"], ["e"]]
