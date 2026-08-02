"""Legacy Chroma/RAG knowledge runtime gate tests."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi.routing import APIRoute

from app.api.knowledge import (
    _ensure_legacy_knowledge_runtime_enabled,
    router,
)
from app.api.safety import router as safety_router
from app.config import settings


LEGACY_VECTOR_ENDPOINTS = {
    "/knowledge/stats",
    "/knowledge/documents",
    "/knowledge/documents/text",
    "/knowledge/documents/course/files",
    "/knowledge/documents/course",
    "/knowledge/documents/upload",
    "/knowledge/search",
    "/knowledge/ask",
    "/knowledge/documents/source",
    "/knowledge/documents/all",
    "/knowledge/gene-drug-rules",
    "/knowledge/init/health-basics",
}


def test_every_legacy_vector_endpoint_has_the_shared_runtime_gate():
    routes = {
        route.path: route
        for route in router.routes
        if isinstance(route, APIRoute)
    }

    assert LEGACY_VECTOR_ENDPOINTS <= routes.keys()
    for path in LEGACY_VECTOR_ENDPOINTS:
        dependency_calls = {
            dependency.call
            for dependency in routes[path].dependant.dependencies
        }
        assert _ensure_legacy_knowledge_runtime_enabled in dependency_calls

    gene_upload_dependencies = {
        dependency.call
        for dependency in routes[
            "/knowledge/gene-knowledge"
        ].dependant.dependencies
    }
    assert (
        _ensure_legacy_knowledge_runtime_enabled
        not in gene_upload_dependencies
    )

    safety_routes = {
        route.path: route
        for route in safety_router.routes
        if isinstance(route, APIRoute)
    }
    safety_index_dependencies = {
        dependency.call
        for dependency in safety_routes[
            "/safety/knowledge/index"
        ].dependant.dependencies
    }
    assert (
        _ensure_legacy_knowledge_runtime_enabled
        in safety_index_dependencies
    )


def test_legacy_vector_search_runtime_endpoint_is_disabled_by_default(
    client,
    auth_user_and_headers,
):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/knowledge/search",
        headers=headers,
        json={"query": "MTHFR", "n_results": 3},
    )

    assert response.status_code == 410
    body = response.json()
    assert body["detail"]["code"] == "legacy_knowledge_runtime_disabled"
    assert body["detail"]["use"] == "system_knowledge"


def test_legacy_rag_ask_runtime_endpoint_is_disabled_by_default(
    client,
    auth_user_and_headers,
):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/knowledge/ask",
        headers=headers,
        json={"question": "咖啡因会影响睡眠吗？"},
    )

    assert response.status_code == 410
    body = response.json()
    assert body["detail"]["code"] == "legacy_knowledge_runtime_disabled"
    assert body["detail"]["use"] == "system_knowledge"


def test_safety_legacy_index_rebuild_is_disabled_before_import(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    _, headers = auth_user_and_headers
    fake_indexer = SimpleNamespace(
        build_index=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("disabled route must not touch Chroma")
        )
    )
    monkeypatch.setitem(
        sys.modules,
        "app.agents.knowledge_librarian.indexer",
        fake_indexer,
    )

    response = client.post(
        "/api/v1/safety/knowledge/index",
        headers=headers,
    )

    assert response.status_code == 410
    assert (
        response.json()["detail"]["code"]
        == "legacy_knowledge_runtime_disabled"
    )


def test_safety_legacy_index_rebuild_requires_admin_when_enabled(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    _, headers = auth_user_and_headers
    monkeypatch.setattr(
        settings, "legacy_knowledge_runtime_enabled", True
    )

    response = client.post(
        "/api/v1/safety/knowledge/index",
        headers=headers,
    )

    assert response.status_code == 403


def test_disabled_legacy_index_rebuild_never_imports_or_initializes_chroma(
    monkeypatch,
):
    from app.tasks import maintenance

    monkeypatch.setattr(
        settings, "legacy_knowledge_runtime_enabled", False
    )
    fake_indexer = SimpleNamespace(
        build_index=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("disabled task must not touch Chroma")
        )
    )
    monkeypatch.setitem(
        sys.modules,
        "app.agents.knowledge_librarian.indexer",
        fake_indexer,
    )

    assert maintenance.rebuild_knowledge_index() == {
        "status": "skipped",
        "reason": "legacy_knowledge_runtime_disabled",
    }


def test_legacy_index_rebuild_propagates_indexer_error_status(monkeypatch):
    from app.tasks import maintenance

    monkeypatch.setattr(
        settings, "legacy_knowledge_runtime_enabled", True
    )
    monkeypatch.setitem(
        sys.modules,
        "app.agents.knowledge_librarian.indexer",
        SimpleNamespace(
            build_index=lambda **kwargs: {
                "status": "ok",
                "error": "ChromaDB unavailable",
                "files_scanned": 0,
                "chunks_indexed": 0,
            }
        ),
    )

    result = maintenance.rebuild_knowledge_index()

    assert result["status"] == "error"
    assert result["error"] == "ChromaDB unavailable"
