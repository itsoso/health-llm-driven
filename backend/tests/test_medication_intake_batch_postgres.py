"""PostgreSQL concurrency contract for source-bound medication intake batches."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from pathlib import Path
from threading import Barrier, Event
import uuid
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.medication import Medication, MedicationLog
from app.models.user import User
from app.models.write_intent import WriteIntent
from app.services import medication_intake_batch as batch
from app.services import medication_safety, write_intent_service
from app.services.managed_migrations import apply_managed_migrations


_TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
_POSTGRES_TEST_ENABLED = bool(
    _TEST_DATABASE_URL
    and make_url(_TEST_DATABASE_URL).get_backend_name() == "postgresql"
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_TEST_ENABLED,
    reason="requires TEST_DATABASE_URL PostgreSQL",
)

_WORKERS = 6
_MESSAGE = "记录服用两种胃药：伊托必利 替普瑞酮 各一粒"
_FROZEN_NOW = datetime(
    2026,
    7,
    21,
    18,
    32,
    tzinfo=ZoneInfo("Asia/Shanghai"),
)


def _attach_completed_medication_preview(
    db,
    *,
    source_message_id: int,
    intent_id: int,
) -> AgentMessage:
    """Persist the exact informed-consent surface required by confirmation."""
    source = db.get(AgentMessage, source_message_id)
    intent = db.get(WriteIntent, intent_id)
    assert source is not None
    assert intent is not None
    payload = intent.payload
    turn_id = f"medication-batch-pg-{source.id}"
    source.client_turn_id = turn_id
    assistant = AgentMessage(
        conversation_id=source.conversation_id,
        role="assistant",
        content="请确认这组用药记录。",
        client_turn_id=turn_id,
        meta={
            "client_turn_id": turn_id,
            "completion_status": "complete",
            "client_turn_finalized": True,
            "pending_write_intent_ids": [intent.id],
            "pending_write_intent_kinds": [batch.WRITE_INTENT_KIND],
            "write_receipts": [],
            "cards": [{
                "type": "medication_draft",
                "data": {
                    "write_intent_id": intent.id,
                    "plan_sha256": payload["plan_sha256"],
                    "items": payload["items"],
                    "taken_at": f"{payload['taken_date']} {payload['taken_time']}",
                },
                "actions": [{
                    "id": f"medication-batch-confirm:{intent.id}",
                    "action": "write_intent.confirm",
                    "label": "确认记录",
                    "endpoint": f"/write-intents/{intent.id}/confirm",
                    "payload": {"write_intent_id": intent.id},
                    "requires_manual_confirm": True,
                }, {
                    "id": f"medication-batch-dismiss:{intent.id}",
                    "action": "write_intent.dismiss",
                    "label": "取消",
                    "endpoint": f"/write-intents/{intent.id}/dismiss",
                    "payload": {"write_intent_id": intent.id},
                    "requires_manual_confirm": True,
                }],
            }],
        },
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)
    return assistant


def test_postgres_migration_upgrades_legacy_write_intents_idempotently(
    tmp_path: Path,
):
    assert _TEST_DATABASE_URL is not None
    schema = f"med_batch_migration_{uuid.uuid4().hex}"
    admin_engine = create_engine(_TEST_DATABASE_URL)
    migration_engine = None
    try:
        with admin_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        migration_engine = create_engine(
            _TEST_DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        with migration_engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE write_intents ("
                "id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, "
                "kind VARCHAR(40) NOT NULL, target_type VARCHAR(40), "
                "target_id INTEGER, executed_ref VARCHAR(100))"
            ))

        migration_id = "20260721_190000_medication_intake_batch_source"
        source = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "managed"
            / f"{migration_id}.postgresql.sql"
        )
        isolated = tmp_path / "postgresql-managed"
        isolated.mkdir()
        (isolated / source.name).write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        first = apply_managed_migrations(migration_engine, isolated)
        replay = apply_managed_migrations(migration_engine, isolated)

        assert [migration.id for migration in first.applied] == [migration_id]
        assert [migration.id for migration in replay.skipped] == [migration_id]
        executed_ref = next(
            column
            for column in inspect(migration_engine).get_columns("write_intents")
            if column["name"] == "executed_ref"
        )
        assert executed_ref["type"].length == 255
        decision_status = next(
            column
            for column in inspect(migration_engine).get_columns("write_intents")
            if column["name"] == "decision_status"
        )
        assert decision_status["type"].length == 20
        with migration_engine.begin() as conn:
            index_definition = conn.execute(text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND indexname = 'uq_write_intents_medication_batch_source'"
            )).scalar_one()
        normalized_index = " ".join(index_definition.lower().split())
        assert "create unique index" in normalized_index
        assert " where " in normalized_index
        assert "kind" in normalized_index
        assert "'medication_intake_batch'" in normalized_index
        assert "target_type" in normalized_index
        assert "'agent_message'" in normalized_index

        insert = text(
            "INSERT INTO write_intents (user_id, kind, target_type, target_id) "
            "VALUES (1, 'medication_intake_batch', 'agent_message', 41)"
        )
        with migration_engine.begin() as conn:
            conn.execute(insert)
        with pytest.raises(IntegrityError):
            with migration_engine.begin() as conn:
                conn.execute(insert)
        with migration_engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO write_intents "
                "(user_id, kind, target_type, target_id) VALUES "
                "(1, 'measurement_prompt', 'agent_message', 41), "
                "(1, 'measurement_prompt', 'agent_message', 41)"
            ))
    finally:
        if migration_engine is not None:
            migration_engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def test_postgres_concurrent_medication_batch_is_source_and_execution_idempotent(
    db,
    monkeypatch,
):
    assert db.get_bind().dialect.name == "postgresql"

    user = User(
        username="medication-batch-pg-concurrency",
        email="medication-batch-pg-concurrency@example.com",
        hashed_password="hashed",
        name="Medication Batch PG Concurrency",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.flush()
    conversation = AgentConversation(
        user_id=user.id,
        title="Medication batch PostgreSQL concurrency",
    )
    db.add(conversation)
    db.flush()
    source = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content=_MESSAGE,
    )
    db.add(source)
    db.commit()
    user_id = user.id
    conversation_id = conversation.id
    source_message_id = source.id
    db.rollback()

    Session = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
    )

    # Every worker reaches commit only after all six have passed the service's
    # pre-insert lookup. PostgreSQL's partial unique index therefore resolves a
    # real concurrent insert race rather than a sequence of ordinary retries.
    proposal_commit_barrier = Barrier(_WORKERS)

    def propose(_index: int):
        session = Session()
        original_commit = session.commit

        def synchronized_commit():
            proposal_commit_barrier.wait(timeout=15)
            return original_commit()

        session.commit = synchronized_commit
        try:
            intent = batch.propose_medication_intake_batch(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                source_message_id=source_message_id,
                text=_MESSAGE,
                reference_now=_FROZEN_NOW,
            )
            return intent.id, intent.payload["plan_sha256"]
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        proposed = list(pool.map(propose, range(_WORKERS)))

    assert len({intent_id for intent_id, _plan_hash in proposed}) == 1
    assert len({plan_hash for _intent_id, plan_hash in proposed}) == 1
    intent_id = proposed[0][0]
    db.expire_all()
    assert (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.kind == batch.WRITE_INTENT_KIND,
            WriteIntent.target_type == "agent_message",
            WriteIntent.target_id == source_message_id,
        )
        .count()
        == 1
    )
    db.rollback()
    _attach_completed_medication_preview(
        db,
        source_message_id=source_message_id,
        intent_id=intent_id,
    )
    db.rollback()

    # Keep safety evaluation out of this database race test; the shared safety
    # service has its own coverage and is invoked only by the single claim winner.
    monkeypatch.setattr(
        medication_safety,
        "evaluate_medication_safety_alerts",
        lambda _db, _user_id, **kwargs: [],
    )

    # The event fires after each worker's initial SELECT but before its atomic
    # pending -> executed UPDATE reaches PostgreSQL. This forces all six sessions
    # to contend on the same production claim statement.
    claim_barrier = Barrier(_WORKERS)

    def synchronize_claim(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("update write_intents set status="):
            claim_barrier.wait(timeout=15)

    event.listen(db.get_bind(), "before_cursor_execute", synchronize_claim)

    def confirm(_index: int):
        session = Session()
        try:
            result = write_intent_service.confirm(session, user_id, intent_id)
            return {
                "idempotent": result["idempotent"],
                "status": result["status"],
                "executed_ref": result["executed_ref"],
                "receipt_ids": tuple(
                    receipt["resource_id"]
                    for receipt in result.get("write_receipts", [])
                ),
                "safety_alerts": tuple(result.get("safety_alerts", [])),
            }
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            confirmed = list(pool.map(confirm, range(_WORKERS)))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", synchronize_claim)

    assert sum(not result["idempotent"] for result in confirmed) == 1
    assert {result["status"] for result in confirmed} == {"executed"}
    assert len({result["executed_ref"] for result in confirmed}) == 1
    receipt_sets = {result["receipt_ids"] for result in confirmed}
    assert len(receipt_sets) == 1
    assert len(next(iter(receipt_sets))) == 2
    assert {result["safety_alerts"] for result in confirmed} == {()}

    db.expire_all()
    final_intent = db.get(WriteIntent, intent_id)
    assert final_intent is not None
    assert final_intent.status == "executed"
    assert db.query(Medication).filter(Medication.user_id == user_id).count() == 2
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user_id).count() == 2


def test_postgres_confirm_wins_before_stale_dismiss_update(
    db,
    monkeypatch,
):
    """Dismiss must use pending-state CAS and never overwrite an executed batch."""
    assert db.get_bind().dialect.name == "postgresql"
    user = User(
        username="medication-batch-pg-dismiss-race",
        email="medication-batch-pg-dismiss-race@example.com",
        hashed_password="hashed",
        name="Medication Batch Dismiss Race",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.flush()
    conversation = AgentConversation(user_id=user.id, title="Dismiss race")
    db.add(conversation)
    db.flush()
    source = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content=_MESSAGE,
    )
    db.add(source)
    db.commit()
    intent = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        text=_MESSAGE,
        reference_now=_FROZEN_NOW,
    )
    user_id = user.id
    intent_id = intent.id
    _attach_completed_medication_preview(
        db,
        source_message_id=source.id,
        intent_id=intent_id,
    )
    db.rollback()

    monkeypatch.setattr(
        medication_safety,
        "evaluate_medication_safety_alerts",
        lambda _db, _user_id, **kwargs: [],
    )
    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    dismiss_before_update = Event()
    confirm_committed = Event()

    def order_dismiss_after_confirm(
        conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        normalized = " ".join(statement.lower().split())
        if (
            conn.info.get("medication_batch_race_role") == "dismiss"
            and normalized.startswith("update write_intents set status=")
        ):
            dismiss_before_update.set()
            assert confirm_committed.wait(timeout=15)

    event.listen(db.get_bind(), "before_cursor_execute", order_dismiss_after_confirm)

    def dismiss():
        session = Session()
        try:
            session.connection().info["medication_batch_race_role"] = "dismiss"
            return write_intent_service.dismiss(session, user_id, intent_id)
        finally:
            session.close()

    def confirm():
        assert dismiss_before_update.wait(timeout=15)
        session = Session()
        try:
            result = write_intent_service.confirm(session, user_id, intent_id)
            confirm_committed.set()
            return result
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            dismiss_future = pool.submit(dismiss)
            confirm_future = pool.submit(confirm)
            dismiss_result = dismiss_future.result(timeout=30)
            confirm_result = confirm_future.result(timeout=30)
    finally:
        confirm_committed.set()
        event.remove(db.get_bind(), "before_cursor_execute", order_dismiss_after_confirm)

    assert confirm_result["status"] == "executed"
    assert dismiss_result["status"] == "executed"
    db.expire_all()
    assert db.get(WriteIntent, intent_id).status == "executed"
    assert (
        db.query(MedicationLog)
        .filter(MedicationLog.user_id == user_id)
        .count()
        == 2
    )


def test_postgres_dismiss_wins_before_stale_confirm_update(
    db,
    monkeypatch,
):
    """A confirm that read pending first must not write after dismiss commits."""
    assert db.get_bind().dialect.name == "postgresql"
    user = User(
        username="medication-batch-pg-reverse-race",
        email="medication-batch-pg-reverse-race@example.com",
        hashed_password="hashed",
        name="Medication Batch Reverse Race",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.flush()
    conversation = AgentConversation(user_id=user.id, title="Reverse dismiss race")
    db.add(conversation)
    db.flush()
    source = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content=_MESSAGE,
    )
    db.add(source)
    db.commit()
    intent = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        text=_MESSAGE,
        reference_now=_FROZEN_NOW,
    )
    user_id = user.id
    source_message_id = source.id
    intent_id = intent.id
    _attach_completed_medication_preview(
        db,
        source_message_id=source_message_id,
        intent_id=intent_id,
    )
    db.rollback()

    monkeypatch.setattr(
        medication_safety,
        "evaluate_medication_safety_alerts",
        lambda _db, _user_id, **kwargs: pytest.fail(
            "dismissed confirmation must not run safety evaluation"
        ),
    )
    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    confirm_before_update = Event()
    dismiss_committed = Event()

    def order_confirm_after_dismiss(
        conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        normalized = " ".join(statement.lower().split())
        if (
            conn.info.get("medication_batch_reverse_race_role") == "confirm"
            and normalized.startswith("update write_intents set status=")
        ):
            confirm_before_update.set()
            assert dismiss_committed.wait(timeout=15)

    event.listen(db.get_bind(), "before_cursor_execute", order_confirm_after_dismiss)

    def confirm():
        session = Session()
        session.connection().info["medication_batch_reverse_race_role"] = "confirm"
        try:
            return write_intent_service.confirm(session, user_id, intent_id)
        finally:
            session.close()

    def dismiss():
        assert confirm_before_update.wait(timeout=15)
        session = Session()
        try:
            result = write_intent_service.dismiss(session, user_id, intent_id)
            dismiss_committed.set()
            return result
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            confirm_future = pool.submit(confirm)
            dismiss_future = pool.submit(dismiss)
            confirm_result = confirm_future.result(timeout=30)
            dismiss_result = dismiss_future.result(timeout=30)
    finally:
        dismiss_committed.set()
        event.remove(db.get_bind(), "before_cursor_execute", order_confirm_after_dismiss)

    assert dismiss_result["status"] == "dismissed"
    assert confirm_result["status"] == "dismissed"
    assert confirm_result["idempotent"] is True
    db.expire_all()
    assert db.get(WriteIntent, intent_id).status == "dismissed"
    assert (
        db.query(MedicationLog)
        .filter(MedicationLog.user_id == user_id)
        .count()
        == 0
    )
