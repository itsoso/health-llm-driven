from __future__ import annotations

from scripts import import_system_kb_v2_artifacts as import_script


def test_import_script_reindexes_after_artifact_import(monkeypatch):
    calls = []

    def fake_import(db, artifact_dir, *, actor):
        calls.append(("import", db, artifact_dir, actor))
        return {
            "documents": 2,
            "edges": 1,
            "changed_document_ids": ["claim:one"],
        }

    def fake_reindex(db, *, actor, changed_document_ids):
        calls.append(("reindex", db, actor, changed_document_ids))
        return {
            "reindex": {"documents": 2, "dense_vectors": 2},
            "pgvector": {"current_vector_backend": "pgvector:text-embedding-v3"},
        }

    monkeypatch.setattr(
        "app.services.system_knowledge_importer.import_system_kb_artifacts",
        fake_import,
    )
    monkeypatch.setattr(
        "app.services.system_knowledge_service.run_system_kb_reindex_report",
        fake_reindex,
    )
    db = object()

    result = import_script.import_artifacts_and_optionally_reindex(
        db,
        "/tmp/system-kb",
        actor="test:import",
    )

    assert calls == [
        ("import", db, "/tmp/system-kb", "test:import"),
        ("reindex", db, "test:import", ["claim:one"]),
    ]
    assert result["import"]["documents"] == 2
    assert result["reindex"]["reindex"]["dense_vectors"] == 2


def test_import_script_can_skip_reindex(monkeypatch):
    calls = []

    def fake_import(db, artifact_dir, *, actor):
        calls.append(("import", db, artifact_dir, actor))
        return {"documents": 2, "edges": 1}

    def fail_reindex(db, *, actor):
        raise AssertionError("reindex should be skipped")

    monkeypatch.setattr(
        "app.services.system_knowledge_importer.import_system_kb_artifacts",
        fake_import,
    )
    monkeypatch.setattr(
        "app.services.system_knowledge_service.run_system_kb_reindex_report",
        fail_reindex,
    )
    db = object()

    result = import_script.import_artifacts_and_optionally_reindex(
        db,
        "/tmp/system-kb",
        actor="test:import",
        skip_reindex=True,
    )

    assert calls == [("import", db, "/tmp/system-kb", "test:import")]
    assert result == {"import": {"documents": 2, "edges": 1}, "reindex": None}
