"""DB guardrails for source-bound medication intake batch intents."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.write_intent import WriteIntent
from app.services.managed_migrations import apply_managed_migrations
from tests.conftest import create_authenticated_user


INDEX_NAME = "uq_write_intents_medication_batch_source"
MIGRATION_ID = "20260721_190000_medication_intake_batch_source"


def _intent(user_id: int, *, kind: str = "medication_intake_batch", target_id: int = 41):
    return WriteIntent(
        user_id=user_id,
        kind=kind,
        title="用药记录待确认",
        status="pending",
        source="agent",
        trust_tier="manual_confirm",
        target_type="agent_message",
        target_id=target_id,
        payload={},
    )


def test_model_partial_unique_index_rejects_duplicate_batch_source(db):
    """同一用户消息至多生成一个批量用药意图，其他 kind/消息不被误伤。"""
    user, _ = create_authenticated_user(db)
    db.add(_intent(user.id))
    db.commit()

    db.add(_intent(user.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(_intent(user.id, kind="measurement_prompt"))
    db.add(_intent(user.id, target_id=42))
    db.commit()


def test_model_executed_ref_can_hold_eight_postgres_integer_ids():
    column = WriteIntent.__table__.c.executed_ref
    worst_case_ref = "medication_logs:" + ",".join(["2147483647"] * 8)

    assert len(worst_case_ref) == 103
    assert column.type.length is not None
    assert column.type.length >= len(worst_case_ref)


def test_model_has_durable_logical_decision_status():
    column = WriteIntent.__table__.c.decision_status

    assert column.nullable is True
    assert column.type.length == 20


def test_managed_migration_pair_enforces_batch_source_uniqueness(tmp_path: Path):
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / f"{MIGRATION_ID}.sqlite.sql"
    postgres_file = migrations_dir / f"{MIGRATION_ID}.postgresql.sql"

    assert sqlite_file.exists()
    assert postgres_file.exists()
    postgres_sql = postgres_file.read_text(encoding="utf-8")
    assert INDEX_NAME in postgres_sql
    assert "ALTER COLUMN executed_ref TYPE VARCHAR(255)" in postgres_sql
    assert "ADD COLUMN IF NOT EXISTS decision_status VARCHAR(20)" in postgres_sql
    assert "WHERE kind = 'medication_intake_batch'" in postgres_sql
    assert "target_type = 'agent_message'" in postgres_sql

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(
        sqlite_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE write_intents ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, kind VARCHAR(40) NOT NULL, "
            "target_type VARCHAR(40), target_id INTEGER)"
        ))

    result = apply_managed_migrations(engine, isolated)

    assert [migration.id for migration in result.applied] == [MIGRATION_ID]
    assert INDEX_NAME in {
        index["name"] for index in inspect(engine).get_indexes("write_intents")
    }
    assert "decision_status" in {
        column["name"] for column in inspect(engine).get_columns("write_intents")
    }
    insert = (
        "INSERT INTO write_intents (user_id, kind, target_type, target_id) "
        "VALUES (:user_id, :kind, :target_type, :target_id)"
    )
    batch_params = {
        "user_id": 1,
        "kind": "medication_intake_batch",
        "target_type": "agent_message",
        "target_id": 41,
    }
    with engine.begin() as conn:
        conn.execute(text(insert), batch_params)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(insert), batch_params)

    with engine.begin() as conn:
        conn.execute(text(insert), {**batch_params, "kind": "measurement_prompt"})
        conn.execute(text(insert), {**batch_params, "target_id": 42})
