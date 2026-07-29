from __future__ import annotations

import builtins
import json
from pathlib import Path
import runpy
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.models.system_knowledge import KBDocument
from app.services import system_knowledge_importer, system_knowledge_service
from app.services.system_knowledge_release_policy import (
    SEALED_RUNTIME_ONLY_DOCUMENT_TYPES,
    SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY,
)
from scripts import (
    quarantine_runtime_only_kb,
    verify_runtime_only_kb_contract as contract_probe,
)


SEED_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "system_kb_v2_seed"
    / "review_manifest.json"
)


def _write_reviewed_claim(artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "claims.jsonl").write_text(
        json.dumps(
            {
                "doc_id": "claim:lock-probe",
                "doc_type": "claim",
                "title": "lock probe",
                "metadata": {"review_status": "reviewed"},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _manifest() -> dict:
    return json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))


def test_postgres_importer_and_quarantine_take_the_same_transaction_lock(
    db,
    tmp_path,
    monkeypatch,
):
    artifact_dir = tmp_path / "artifacts"
    _write_reviewed_claim(artifact_dir)
    real_execute = db.execute
    captured: list[tuple[str, dict]] = []

    def capture_lock(statement, params=None, *args, **kwargs):
        sql = str(statement)
        if "pg_advisory_xact_lock" in sql:
            captured.append((sql, dict(params or {})))
            # The backing database is still SQLite. Restore its public dialect
            # name immediately after exercising the PostgreSQL lock branch.
            monkeypatch.setattr(db.get_bind().dialect, "name", "sqlite")
            return None
        return real_execute(statement, params, *args, **kwargs)

    monkeypatch.setattr(db, "execute", capture_lock)
    monkeypatch.setattr(db.get_bind().dialect, "name", "postgresql")
    system_knowledge_importer.import_system_kb_artifacts(
        db,
        artifact_dir,
        actor="test:lock-import",
    )

    monkeypatch.setattr(db.get_bind().dialect, "name", "postgresql")
    quarantine_runtime_only_kb.quarantine_runtime_only_documents(
        db,
        manifest=_manifest(),
        actor="test:lock-quarantine",
    )

    assert len(captured) == 2
    assert all("pg_advisory_xact_lock" in sql for sql, _ in captured)
    assert captured[0][1] == captured[1][1]
    assert len(captured[0][1]) == 1


def test_sqlite_importer_and_quarantine_do_not_execute_advisory_lock_sql(
    db,
    tmp_path,
    monkeypatch,
):
    if db.get_bind().dialect.name != "sqlite":
        pytest.skip("SQLite no-op contract requires the SQLite test backend")

    artifact_dir = tmp_path / "artifacts"
    _write_reviewed_claim(artifact_dir)
    real_execute = db.execute
    advisory_statements: list[str] = []

    def capture_execute(statement, params=None, *args, **kwargs):
        sql = str(statement)
        if "pg_advisory_xact_lock" in sql:
            advisory_statements.append(sql)
        return real_execute(statement, params, *args, **kwargs)

    monkeypatch.setattr(db, "execute", capture_execute)
    system_knowledge_importer.import_system_kb_artifacts(
        db,
        artifact_dir,
        actor="test:sqlite-import",
    )
    quarantine_runtime_only_kb.quarantine_runtime_only_documents(
        db,
        manifest=_manifest(),
        actor="test:sqlite-quarantine",
    )

    assert advisory_statements == []
    assert db.get(KBDocument, "claim:lock-probe") is not None


def test_staged_quarantine_remains_self_contained_for_pre_feature_rollback(
    monkeypatch,
):
    real_import = builtins.__import__
    helper_module = "app.services.system_knowledge_release_policy"

    def import_without_release_helper(name, *args, **kwargs):
        if name == helper_module:
            raise ModuleNotFoundError(
                "simulated pre-feature rollback target",
                name=helper_module,
            )
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_release_helper)
    namespace = runpy.run_path(
        str(
            Path(quarantine_runtime_only_kb.__file__).resolve()
        ),
        run_name="staged_quarantine_probe",
    )

    assert namespace["SEALED_RUNTIME_ONLY_DOCUMENT_TYPES"] == dict(
        SEALED_RUNTIME_ONLY_DOCUMENT_TYPES
    )
    assert (
        namespace["SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY"]
        == SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY
    )


def test_postgres_quarantine_finishes_after_an_inflight_import_and_wins(
    db,
    tmp_path,
    monkeypatch,
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("transaction advisory lock concurrency requires PostgreSQL")

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(parents=True)
    target_id = _manifest()["authority_packs"][0]["claim_ids"][0]
    (artifact_dir / "claims.jsonl").write_text(
        json.dumps(
            {
                "doc_id": target_id,
                "doc_type": "claim",
                "title": "sealed lock probe",
                "metadata": {"review_status": "reviewed"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    session_factory = sessionmaker(bind=db.get_bind())
    importer_locked = threading.Event()
    allow_importer_to_finish = threading.Event()
    quarantine_attempting_lock = threading.Event()
    quarantine_done = threading.Event()
    failures: list[BaseException] = []
    acquire_lock = (
        system_knowledge_importer.acquire_system_kb_release_mutation_lock
    )

    def pause_importer_after_lock(session):
        acquire_lock(session)
        importer_locked.set()
        if not allow_importer_to_finish.wait(timeout=10):
            raise TimeoutError("test did not release the importer")

    def note_quarantine_lock_attempt(session):
        quarantine_attempting_lock.set()
        acquire_lock(session)

    monkeypatch.setattr(
        system_knowledge_importer,
        "acquire_system_kb_release_mutation_lock",
        pause_importer_after_lock,
    )
    monkeypatch.setattr(
        quarantine_runtime_only_kb,
        "acquire_system_kb_release_mutation_lock",
        note_quarantine_lock_attempt,
    )

    def run_importer():
        session = session_factory()
        try:
            system_knowledge_importer.import_system_kb_artifacts(
                session,
                artifact_dir,
                actor="test:concurrent-import",
            )
        except BaseException as exc:  # noqa: BLE001 - surface thread failure
            failures.append(exc)
        finally:
            session.close()

    def run_quarantine():
        session = session_factory()
        try:
            quarantine_runtime_only_kb.quarantine_runtime_only_documents(
                session,
                manifest=_manifest(),
                actor="test:concurrent-quarantine",
            )
        except BaseException as exc:  # noqa: BLE001 - surface thread failure
            failures.append(exc)
        finally:
            quarantine_done.set()
            session.close()

    importer_thread = threading.Thread(target=run_importer, daemon=True)
    quarantine_thread = threading.Thread(target=run_quarantine, daemon=True)
    try:
        importer_thread.start()
        assert importer_locked.wait(timeout=5)
        quarantine_thread.start()
        assert quarantine_attempting_lock.wait(timeout=5)
        assert quarantine_done.wait(timeout=0.1) is False
    finally:
        allow_importer_to_finish.set()

    importer_thread.join(timeout=10)
    quarantine_thread.join(timeout=10)
    assert not importer_thread.is_alive()
    assert not quarantine_thread.is_alive()
    assert failures == []

    db.expire_all()
    stored = db.get(KBDocument, target_id)
    assert stored is not None
    assert stored.is_archived is True


def test_postgres_probe_vector_error_keeps_importer_blocked_until_outer_rollback(
    db,
    tmp_path,
    monkeypatch,
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("transaction lock survivability requires PostgreSQL")

    artifact_dir = tmp_path / "artifacts"
    target_id = "claim:probe-vector-error-lock-survival"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "claims.jsonl").write_text(
        json.dumps(
            {
                "doc_id": target_id,
                "doc_type": "claim",
                "title": "vector error lock survival",
                "metadata": {"review_status": "reviewed"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    session_factory = sessionmaker(bind=db.get_bind())
    probe_session = session_factory()
    importer_attempting_lock = threading.Event()
    importer_done = threading.Event()
    failures: list[BaseException] = []
    real_acquire = (
        system_knowledge_importer.acquire_system_kb_release_mutation_lock
    )

    def _note_importer_lock_attempt(session):
        importer_attempting_lock.set()
        real_acquire(session)

    monkeypatch.setattr(
        system_knowledge_importer,
        "acquire_system_kb_release_mutation_lock",
        _note_importer_lock_attempt,
    )
    monkeypatch.setattr(
        system_knowledge_service,
        "PGVECTOR_TABLE",
        "kb_document_embeddings_probe_table_that_does_not_exist",
    )
    monkeypatch.setattr(
        system_knowledge_service,
        "_embed_system_kb_texts",
        lambda texts: [[0.1] for _text in texts],
    )
    monkeypatch.setattr(
        system_knowledge_service,
        "_pgvector_literal",
        lambda vector: "[0.1]",
    )

    def _run_importer():
        session = session_factory()
        try:
            system_knowledge_importer.import_system_kb_artifacts(
                session,
                artifact_dir,
                actor="test:probe-vector-error-concurrent-import",
            )
        except BaseException as exc:  # noqa: BLE001 - surface thread failure
            failures.append(exc)
        finally:
            importer_done.set()
            session.close()

    importer_thread = threading.Thread(target=_run_importer, daemon=True)
    try:
        real_acquire(probe_session)
        probe_backend_pid = probe_session.execute(
            text("SELECT pg_backend_pid()")
        ).scalar_one()
        contract_probe._assert_system_kb_release_mutation_lock_held(
            probe_session
        )
        protected_session = (
            contract_probe._TransactionPreservingProbeSession(probe_session)
        )
        with pytest.raises(RuntimeError, match="attempted to rollback"):
            system_knowledge_service._rank_pgvector_documents(
                protected_session,
                {},
                "force vector SQL error",
                limit=5,
            )

        observer_session = session_factory()
        try:
            advisory_locks = observer_session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM pg_locks
                    WHERE locktype = 'advisory'
                      AND pid = :probe_backend_pid
                      AND granted
                    """
                ),
                {"probe_backend_pid": probe_backend_pid},
            ).scalar_one()
        finally:
            observer_session.close()
        assert advisory_locks == 1

        importer_thread.start()
        assert importer_attempting_lock.wait(timeout=5)
        assert importer_done.wait(timeout=0.2) is False, failures
    finally:
        probe_session.rollback()
        probe_session.close()

    importer_thread.join(timeout=10)
    assert not importer_thread.is_alive()
    assert failures == []
    db.expire_all()
    stored = db.get(KBDocument, target_id)
    assert stored is not None
