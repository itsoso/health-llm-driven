from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import event

from app.models.system_knowledge import KBDocument, KBDocumentVector, KBEdge
from app.services import system_knowledge_importer
from app.services import system_knowledge_service
from app.services.system_knowledge_importer import import_system_kb_artifacts


_DOCUMENT_FILES = (
    "entities.jsonl",
    "claims.jsonl",
    "pages.jsonl",
    "protocols.jsonl",
    "contraindications.jsonl",
    "eval_cases.jsonl",
)


def _write_documents(
    root: Path,
    documents: list[dict],
    relations: list[dict] | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for file_name in _DOCUMENT_FILES:
        rows = documents if file_name == "claims.jsonl" else []
        (root / file_name).write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    relation_rows = relations or []
    (root / "relations.jsonl").write_text(
        "".join(json.dumps(relation, sort_keys=True) + "\n" for relation in relation_rows),
        encoding="utf-8",
    )
    counts = {Path(file_name).stem: 0 for file_name in _DOCUMENT_FILES}
    counts["claims"] = len(documents)
    counts["relations"] = len(relation_rows)
    (root / "manifest.json").write_text(
        json.dumps({"version": "test", "counts": counts}, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _claim(doc_id: str, *, title: str | None = None) -> dict:
    return {
        "doc_id": doc_id,
        "doc_type": "claim",
        "title": title or doc_id,
        "summary": f"summary for {doc_id}",
        "metadata": {"review_status": "reviewed", "source": "test"},
    }


def test_unchanged_import_reports_no_changed_documents_and_sparse_reindex_is_noop(
    db,
    tmp_path,
):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one"), _claim("claim:two")])

    first = import_system_kb_artifacts(db, artifact_dir, actor="test:first")
    first_reindex = system_knowledge_service.reindex_knowledge_documents(db, actor="test:first")
    second = import_system_kb_artifacts(db, artifact_dir, actor="test:second")
    second_reindex = system_knowledge_service.reindex_knowledge_documents(db, actor="test:second")

    assert first["changed_document_ids"] == ["claim:one", "claim:two"]
    assert set(first["changed_document_hashes"]) == {"claim:one", "claim:two"}
    assert first_reindex["indexed_document_ids"] == ["claim:one", "claim:two"]
    assert second["changed_document_ids"] == []
    assert second["changed_document_hashes"] == {}
    assert second["proof"]["mode"] == "shadow"
    assert second["proof"]["decision"] == "hit"
    assert second["proof"]["scope"] == "declared_artifact_rows"
    assert second["proof"]["skip_eligible"] is False
    assert second["skipped_by_proof"] is False
    assert second_reindex["indexed_document_ids"] == []


def test_one_changed_document_only_rebuilds_its_sparse_vector(db, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one"), _claim("claim:two")])
    import_system_kb_artifacts(db, artifact_dir, actor="test:first")
    system_knowledge_service.reindex_knowledge_documents(db, actor="test:first")
    original_hash = db.get(KBDocumentVector, "claim:one").content_hash

    _write_documents(
        artifact_dir,
        [_claim("claim:one", title="changed title"), _claim("claim:two")],
    )
    imported = import_system_kb_artifacts(db, artifact_dir, actor="test:changed")
    reindexed = system_knowledge_service.reindex_knowledge_documents(db, actor="test:changed")

    assert imported["changed_document_ids"] == ["claim:one"]
    assert imported["changed_document_hashes"]["claim:one"] != original_hash
    assert imported["proof"]["decision"] == "miss"
    assert reindexed["indexed_document_ids"] == ["claim:one"]
    assert db.get(KBDocumentVector, "claim:one").content_hash != original_hash


def test_missing_and_stale_sparse_vectors_are_rebuilt_even_without_import_changes(db, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one"), _claim("claim:two")])
    import_system_kb_artifacts(db, artifact_dir, actor="test:first")
    system_knowledge_service.reindex_knowledge_documents(db, actor="test:first")

    db.delete(db.get(KBDocumentVector, "claim:one"))
    db.get(KBDocumentVector, "claim:two").content_hash = "0" * 64
    db.commit()

    report = system_knowledge_service.reindex_knowledge_documents(db, actor="test:repair")

    assert report["indexed_document_ids"] == ["claim:one", "claim:two"]


def test_sparse_vector_backend_change_invalidates_existing_rows(db, tmp_path, monkeypatch):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one")])
    import_system_kb_artifacts(db, artifact_dir, actor="test:first")
    system_knowledge_service.reindex_knowledge_documents(db, actor="test:first")

    monkeypatch.setattr(system_knowledge_service, "VECTOR_BACKEND", "sparse_term_cosine_v2")
    report = system_knowledge_service.reindex_knowledge_documents(db, actor="test:model-change")

    assert report["indexed_document_ids"] == ["claim:one"]
    assert db.get(KBDocumentVector, "claim:one").embedding_model == "sparse_term_cosine_v2"


def test_dense_vector_model_dimension_and_content_drift_are_stale():
    searchable = {
        "claim:current": ("current", "a" * 64),
        "claim:model": ("model", "b" * 64),
        "claim:dimension": ("dimension", "c" * 64),
        "claim:content": ("content", "d" * 64),
        "claim:missing": ("missing", "e" * 64),
    }
    existing = {
        "claim:current": {
            "embedding_model": "embed-v1",
            "content_hash": "a" * 64,
            "dimensions": 3,
        },
        "claim:model": {
            "embedding_model": "embed-v0",
            "content_hash": "b" * 64,
            "dimensions": 3,
        },
        "claim:dimension": {
            "embedding_model": "embed-v1",
            "content_hash": "c" * 64,
            "dimensions": 2,
        },
        "claim:content": {
            "embedding_model": "embed-v1",
            "content_hash": "f" * 64,
            "dimensions": 3,
        },
    }

    stale = system_knowledge_service._stale_pgvector_document_ids(
        searchable,
        existing,
        embedding_model="embed-v1",
        embedding_dimensions=3,
    )

    assert stale == [
        "claim:content",
        "claim:dimension",
        "claim:missing",
        "claim:model",
    ]


def test_dense_reindex_reports_coverage_and_embeds_only_missing_or_stale_rows(
    monkeypatch,
):
    embedded_texts: list[str] = []
    executed_params: list[list[dict]] = []

    class Connection:
        def execute(self, _statement, params):
            executed_params.append(params)

    class Transaction:
        def __enter__(self):
            return Connection()

        def __exit__(self, exc_type, exc, traceback):
            return False

    class Engine:
        def begin(self):
            return Transaction()

    class Session:
        def get_bind(self):
            return Engine()

    searchable = {
        "claim:current": ("current text", "a" * 64),
        "claim:stale": ("stale text", "b" * 64),
    }
    settings_obj = system_knowledge_service.settings
    monkeypatch.setattr(settings_obj, "system_kb_embedding_model", "embed-v1")
    monkeypatch.setattr(settings_obj, "system_kb_embedding_dimensions", 3)
    monkeypatch.setattr(
        system_knowledge_service,
        "_delete_removed_pgvector_rows",
        lambda *_args: 0,
    )
    monkeypatch.setattr(
        system_knowledge_service,
        "_load_pgvector_index_state",
        lambda *_args: {
            "claim:current": {
                "embedding_model": "embed-v1",
                "content_hash": "a" * 64,
                "dimensions": 3,
            },
            "claim:stale": {
                "embedding_model": "embed-v1",
                "content_hash": "0" * 64,
                "dimensions": 3,
            },
        },
    )

    def embed(texts):
        embedded_texts.extend(texts)
        return [[0.1, 0.2, 0.3] for _text in texts]

    monkeypatch.setattr(system_knowledge_service, "_embed_system_kb_texts", embed)
    monkeypatch.setattr(
        system_knowledge_service,
        "_pgvector_literal",
        lambda vector: json.dumps(vector),
    )

    report = system_knowledge_service._reindex_pgvector_documents(
        Session(),
        searchable,
        table_ready=True,
    )

    assert report == {
        "covered": 2,
        "updated": 1,
        "deleted": 0,
    }
    assert embedded_texts == ["stale text"]
    assert [item["doc_id"] for item in executed_params[0]] == ["claim:stale"]


def test_dense_reindex_cleans_removed_rows_when_no_documents_remain(monkeypatch):
    monkeypatch.setattr(
        system_knowledge_service,
        "_delete_removed_pgvector_rows",
        lambda *_args: 2,
    )

    report = system_knowledge_service._reindex_pgvector_documents(
        object(),
        {},
        table_ready=True,
    )

    assert report == {"covered": 0, "updated": 0, "deleted": 2}


def test_dense_cleanup_evaluates_document_liveness_inside_the_delete_statement():
    executed_sql: list[str] = []

    class Result:
        rowcount = 2

    class Connection:
        def execute(self, statement):
            executed_sql.append(str(statement))
            return Result()

    class Transaction:
        def __enter__(self):
            return Connection()

        def __exit__(self, exc_type, exc, traceback):
            return False

    class Engine:
        def begin(self):
            return Transaction()

    class Session:
        def get_bind(self):
            return Engine()

    deleted = system_knowledge_service._delete_removed_pgvector_rows(Session())

    normalized_sql = " ".join(executed_sql[0].split()).lower()
    assert deleted == 2
    assert "delete from kb_document_embeddings" in normalized_sql
    assert "where not exists" in normalized_sql
    assert "from kb_documents" in normalized_sql
    assert "document.is_archived is false" in normalized_sql


def test_archived_document_indexes_are_cleaned_without_artifact_owned_deletion(
    db,
    tmp_path,
):
    artifact_dir = tmp_path / "artifacts"
    relation = {
        "src_doc_id": "claim:one",
        "dst_doc_id": "claim:two",
        "relation": "supports",
        "confidence": 0.8,
    }
    _write_documents(
        artifact_dir,
        [_claim("claim:one"), _claim("claim:two")],
        [relation],
    )
    import_system_kb_artifacts(db, artifact_dir, actor="test:first")
    system_knowledge_service.reindex_knowledge_documents(db, actor="test:first")

    removed = db.get(KBDocument, "claim:two")
    removed.is_archived = True
    removed.metadata_json = {**(removed.metadata_json or {}), "review_status": "archived"}
    db.commit()
    reindexed = system_knowledge_service.reindex_knowledge_documents(db, actor="test:delete")

    assert db.get(KBDocument, "claim:two").is_archived is True
    assert db.get(KBDocumentVector, "claim:two") is None
    assert reindexed["deleted_sparse_vectors"] == 1


def test_reviewed_but_archived_artifact_document_is_not_relation_eligible(
    db,
    tmp_path,
):
    artifact_dir = tmp_path / "artifacts"
    archived_claim = {
        **_claim("claim:archived"),
        "is_archived": True,
    }
    relation = {
        "src_doc_id": "claim:active",
        "dst_doc_id": "claim:archived",
        "relation": "supports",
        "confidence": 0.8,
    }
    _write_documents(
        artifact_dir,
        [_claim("claim:active"), archived_claim],
        [relation],
    )

    imported = import_system_kb_artifacts(db, artifact_dir, actor="test:archived")

    assert imported["edges"] == 0
    assert imported["skipped_edges"] == 1
    assert db.get(KBDocument, "claim:archived").is_archived is True


def test_shadow_proof_detects_duplicate_declared_relation_rows(db, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    relation = {
        "src_doc_id": "claim:one",
        "dst_doc_id": "claim:two",
        "relation": "supports",
        "confidence": 0.8,
    }
    _write_documents(
        artifact_dir,
        [_claim("claim:one"), _claim("claim:two")],
        [relation],
    )
    import_system_kb_artifacts(db, artifact_dir, actor="test:first")
    db.add(
        KBEdge(
            src_doc_id="claim:one",
            dst_doc_id="claim:two",
            relation="supports",
            confidence=0.8,
        )
    )
    db.commit()

    imported = import_system_kb_artifacts(db, artifact_dir, actor="test:duplicate")

    assert imported["proof"]["decision"] == "miss"
    assert imported["proof"]["reason"] == "drift"
    assert imported["skipped_by_proof"] is False
    assert db.query(KBEdge).count() == 2


def test_whole_import_on_mode_is_fail_closed_without_production_evidence(
    db,
    tmp_path,
    monkeypatch,
):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one")])
    import_system_kb_artifacts(db, artifact_dir, actor="test:first")
    system_knowledge_service.reindex_knowledge_documents(db, actor="test:first")
    monkeypatch.setenv("SYSTEM_KB_IMPORT_PROOF_MODE", "on")

    result = import_system_kb_artifacts(db, artifact_dir, actor="test:on-disabled")

    assert result["proof"]["mode"] == "off"
    assert result["proof"]["reason"] == "unproven_skip_mode"
    assert result["skipped_by_proof"] is False


def test_invalid_whole_import_proof_mode_falls_back_to_full_import(db, tmp_path, monkeypatch):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one")])
    monkeypatch.setenv("SYSTEM_KB_IMPORT_PROOF_MODE", "unexpected")

    result = import_system_kb_artifacts(db, artifact_dir, actor="test:invalid-mode")

    assert result["proof"]["mode"] == "off"
    assert result["proof"]["reason"] == "invalid_mode"
    assert result["skipped_by_proof"] is False


def test_shadow_proof_detects_database_drift_and_full_import_repairs_it(
    db,
    tmp_path,
):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one")])
    import_system_kb_artifacts(db, artifact_dir, actor="test:first")
    system_knowledge_service.reindex_knowledge_documents(db, actor="test:first")
    db.get(KBDocument, "claim:one").title = "database drift"
    db.commit()

    result = import_system_kb_artifacts(db, artifact_dir, actor="test:drift")

    assert result["proof"]["mode"] == "shadow"
    assert result["proof"]["decision"] == "miss"
    assert result["skipped_by_proof"] is False
    assert result["changed_document_ids"] == ["claim:one"]
    assert db.get(KBDocument, "claim:one").title == "claim:one"


def test_import_proof_is_evaluated_only_after_the_release_mutation_lock(
    db,
    tmp_path,
    monkeypatch,
):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one")])
    lock_held = False
    real_evaluate = system_knowledge_importer._evaluate_whole_import_proof

    def acquire(_db):
        nonlocal lock_held
        lock_held = True

    def evaluate(*args, **kwargs):
        assert lock_held is True
        return real_evaluate(*args, **kwargs)

    monkeypatch.setattr(system_knowledge_importer, "acquire_system_kb_release_mutation_lock", acquire)
    monkeypatch.setattr(system_knowledge_importer, "_evaluate_whole_import_proof", evaluate)

    import_system_kb_artifacts(db, artifact_dir, actor="test:lock-order")


def test_removing_a_document_from_one_artifact_source_never_archives_another_source(
    db,
    tmp_path,
):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    _write_documents(first_dir, [_claim("claim:shared")])
    _write_documents(second_dir, [_claim("claim:shared")])

    import_system_kb_artifacts(db, first_dir, actor="test:first-source")
    import_system_kb_artifacts(db, second_dir, actor="test:second-source")
    _write_documents(first_dir, [])
    result = import_system_kb_artifacts(db, first_dir, actor="test:first-removed")

    assert result["deleted_document_ids"] == []
    assert db.get(KBDocument, "claim:shared").is_archived is False


def test_missing_artifact_root_fails_without_database_mutation(db, tmp_path):
    with pytest.raises(ValueError, match="artifact directory"):
        import_system_kb_artifacts(db, tmp_path / "missing", actor="test:missing")

    assert db.query(KBDocument).count() == 0


def test_missing_required_artifact_file_fails_without_database_mutation(db, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one")])
    (artifact_dir / "claims.jsonl").unlink()

    with pytest.raises(ValueError, match="required System KB artifact file"):
        import_system_kb_artifacts(db, artifact_dir, actor="test:missing-file")

    assert db.query(KBDocument).count() == 0


def test_manifest_count_drift_fails_without_database_mutation(db, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one")])
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["counts"]["claims"] = 2
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest count mismatch"):
        import_system_kb_artifacts(db, artifact_dir, actor="test:count-drift")

    assert db.query(KBDocument).count() == 0


def test_truncated_jsonl_fails_without_database_mutation(db, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(artifact_dir, [_claim("claim:one")])
    (artifact_dir / "claims.jsonl").write_text('{"doc_id":', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSONL"):
        import_system_kb_artifacts(db, artifact_dir, actor="test:truncated")

    assert db.query(KBDocument).count() == 0


def test_pgvector_action_items_use_total_coverage_not_incremental_updates():
    pgvector = {
        "latest_reindex_report": {
            "diff": {
                "reindex": {
                    "documents": 2,
                    "dense_vectors": 2,
                    "dense_vectors_updated": 0,
                },
                "pgvector": {
                    "postgres": True,
                    "current_vector_backend": "pgvector:embed-v1",
                },
            }
        }
    }

    assert "kb_pgvector_dense_coverage_low" not in (
        system_knowledge_service._pgvector_action_items(pgvector)
    )


def test_shadow_proof_and_unchanged_import_do_not_query_per_document(db, tmp_path):
    artifact_dir = tmp_path / "artifacts"
    _write_documents(
        artifact_dir,
        [_claim(f"claim:{index}") for index in range(30)],
    )
    import_system_kb_artifacts(db, artifact_dir, actor="test:baseline")
    system_knowledge_service.reindex_knowledge_documents(db, actor="test:baseline")

    statement_count = 0

    def count_statement(*_args):
        nonlocal statement_count
        statement_count += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        import_system_kb_artifacts(db, artifact_dir, actor="test:query-count")
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)

    assert statement_count <= 12
