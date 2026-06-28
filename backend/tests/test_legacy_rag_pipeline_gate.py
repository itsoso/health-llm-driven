"""Runtime gate for the legacy Chroma RAG pipeline."""

from __future__ import annotations

import importlib

from app.config import settings
from app.services.knowledge.rag_pipeline import RAGPipeline


class FakeVectorStore:
    def __init__(self):
        self.available_checks = 0
        self.search_calls = []

    def is_available(self):
        self.available_checks += 1
        return True

    def search(self, query, n_results=5, category=None):
        self.search_calls.append(
            {"query": query, "n_results": n_results, "category": category}
        )
        return [
            {
                "content": "睡眠不足时应优先恢复作息。",
                "metadata": {"title": "睡眠恢复", "category": "sleep"},
                "relevance_score": 0.32,
            },
            {
                "content": "低相关内容",
                "metadata": {"title": "噪声", "category": "sleep"},
                "relevance_score": 0.1,
            },
        ]


def _rag_module():
    return importlib.import_module("app.services.knowledge.rag_pipeline")


def test_legacy_rag_pipeline_disabled_by_default_skips_vector_store(monkeypatch):
    monkeypatch.setattr(settings, "legacy_knowledge_runtime_enabled", False)
    fake_vector_store = FakeVectorStore()
    monkeypatch.setattr(_rag_module(), "vector_store", fake_vector_store)

    pipeline = RAGPipeline()
    pipeline.openai_client = object()

    assert pipeline.is_available() is False
    assert pipeline.retrieve_relevant_knowledge("改善睡眠", category="sleep") == []
    assert fake_vector_store.available_checks == 0
    assert fake_vector_store.search_calls == []


def test_legacy_rag_pipeline_can_be_explicitly_reenabled(monkeypatch):
    monkeypatch.setattr(settings, "legacy_knowledge_runtime_enabled", True)
    fake_vector_store = FakeVectorStore()
    monkeypatch.setattr(_rag_module(), "vector_store", fake_vector_store)

    pipeline = RAGPipeline()
    pipeline.openai_client = object()

    assert pipeline.is_available() is True

    results = pipeline.retrieve_relevant_knowledge(
        "改善睡眠",
        category="sleep",
        n_results=3,
    )

    assert fake_vector_store.search_calls == [
        {"query": "改善睡眠", "n_results": 3, "category": "sleep"}
    ]
    assert [result["metadata"]["title"] for result in results] == ["睡眠恢复"]


def test_generate_with_knowledge_disabled_returns_gate_error(monkeypatch):
    monkeypatch.setattr(settings, "legacy_knowledge_runtime_enabled", False)
    pipeline = RAGPipeline()
    pipeline.openai_client = object()

    def fail_retrieval(*args, **kwargs):
        raise AssertionError("legacy retrieval should not run when disabled")

    monkeypatch.setattr(pipeline, "retrieve_relevant_knowledge", fail_retrieval)

    result = pipeline.generate_with_knowledge(
        user_query="我该怎么改善睡眠?",
        user_context={},
        health_data=None,
        category="sleep",
    )

    assert result == {
        "success": False,
        "error": "legacy_knowledge_runtime_disabled",
        "answer": None,
    }
