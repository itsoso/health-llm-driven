"""Legacy Chroma/RAG knowledge runtime gate tests."""

from __future__ import annotations


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
