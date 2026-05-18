from __future__ import annotations

import json


def test_upload_gene_knowledge_requires_admin(client, auth_user_and_headers):
    user, headers = auth_user_and_headers
    res = client.post(
        "/api/v1/knowledge/gene-knowledge",
        headers=headers,
        json={"version": "v0", "compiled_at": "2026-05-19T00:00:00Z"},
    )
    assert res.status_code == 403


def test_upload_gene_knowledge_persists_payload_and_returns_counts(client, db, auth_user_and_headers, tmp_path, monkeypatch):
    from app.services import gene_rules_registry

    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add(user)
    db.commit()

    target_path = tmp_path / "gene_knowledge.json"
    monkeypatch.setattr(gene_rules_registry, "DEFAULT_PATH", target_path)

    payload = {
        "version": "test",
        "compiled_at": "2026-05-19T00:00:00Z",
        "schema_id": "llm-wiki-v2-gene-knowledge",
        "entities": {"gene": {"CYP2C19": {"id": "CYP2C19"}}},
        "claims": [{"id": "claim:1"}],
        "gene_rules": {
            "CYP2C19": {
                "poor": {
                    "avoid": ["clopidogrel"],
                }
            }
        },
        "snp_registry": {"rs123": {"gene": "CYP2C19"}},
    }

    res = client.post(
        "/api/v1/knowledge/gene-knowledge",
        headers=headers,
        json=payload,
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"] == "test"
    assert body["schema_id"] == "llm-wiki-v2-gene-knowledge"
    assert body["gene_count"] == 1
    assert body["claim_count"] == 1
    assert body["snp_count"] == 1
    assert body["entity_counts"]["gene"] == 1

    persisted = json.loads(target_path.read_text(encoding="utf-8"))
    assert persisted["version"] == "test"
    assert persisted["gene_rules"]["CYP2C19"]["poor"]["avoid"] == ["clopidogrel"]
