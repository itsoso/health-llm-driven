"""Managed migration: drop the legacy supplement_records.taken_count column.

The column exists only in production PostgreSQL: the January 2026 SQLite→PostgreSQL
copy script created it with DEFAULT 1, the ORM never mapped it, and every row holds
1 whether or not the dose was taken, so it carries no intake signal.
"""

from datetime import date
import os
from pathlib import Path
import time
import uuid

import pytest
from sqlalchemy import create_engine, insert, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.models.supplement import SupplementRecord
from app.services.managed_migrations import _split_sql_statements, apply_managed_migrations


MIGRATION_ID = "20260930_120000_drop_supplement_records_taken_count"
MANAGED_DIR = Path(__file__).resolve().parents[1] / "migrations" / "managed"
ROLLBACK_SQL = (
    "ALTER TABLE supplement_records ADD COLUMN IF NOT EXISTS taken_count INTEGER DEFAULT 1"
)
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
POSTGRES_TEST_ENABLED = bool(
    TEST_DATABASE_URL
    and make_url(TEST_DATABASE_URL).get_backend_name() == "postgresql"
)
requires_postgres = pytest.mark.skipif(
    not POSTGRES_TEST_ENABLED,
    reason="requires TEST_DATABASE_URL PostgreSQL",
)

# Production shape: the January copy-script table, the columns added in place later,
# then the managed unique index and the composite index. Rows omit taken_count, as
# every ORM insert does, so the default fills it.
PRODUCTION_TABLE = (
    "CREATE TABLE users (id SERIAL PRIMARY KEY)",
    "CREATE TABLE supplement_definitions (id SERIAL PRIMARY KEY)",
    "CREATE TABLE supplement_records ("
    "id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), "
    "supplement_id INTEGER REFERENCES supplement_definitions(id), "
    "record_date DATE NOT NULL, taken_count INTEGER DEFAULT 1, notes TEXT, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
    "ALTER TABLE supplement_records ADD COLUMN taken BOOLEAN DEFAULT FALSE, "
    "ADD COLUMN taken_time TIME",
    "ALTER TABLE supplement_records ADD COLUMN actual_dosage VARCHAR(40)",
    "CREATE UNIQUE INDEX uq_supprec_supp_date "
    "ON supplement_records (supplement_id, record_date)",
    "CREATE INDEX idx_supplement_records_user_date "
    "ON supplement_records (user_id, record_date, taken)",
    "INSERT INTO users (id) VALUES (1)",
    "INSERT INTO supplement_definitions (id) VALUES (1), (2), (3)",
    "INSERT INTO supplement_records "
    "(user_id, supplement_id, record_date, notes, taken, taken_time, actual_dosage) "
    "VALUES (1, 1, '2026-09-01', 'morning', TRUE, '08:00', '1 capsule'), "
    "(1, 2, '2026-09-01', NULL, FALSE, NULL, NULL)",
)
KEPT_COLUMNS = [
    "id", "user_id", "supplement_id", "record_date", "notes",
    "created_at", "taken", "taken_time", "actual_dosage",
]


@pytest.fixture
def pg_engine():
    schema = f"supp_taken_count_{uuid.uuid4().hex}"
    admin_engine = create_engine(TEST_DATABASE_URL)
    engine = None
    try:
        with admin_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        # statement_timeout is a backstop: a migration that lost its lock_timeout
        # fails the lock test instead of hanging on the test's own blocker.
        engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema} -cstatement_timeout=60000"},
        )
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def _migration_sql(dialect: str) -> str:
    return (MANAGED_DIR / f"{MIGRATION_ID}.{dialect}.sql").read_text(encoding="utf-8")


def _isolated(tmp_path: Path, dialect: str) -> Path:
    isolated = tmp_path / f"{dialect}-managed"
    isolated.mkdir()
    (isolated / f"{MIGRATION_ID}.{dialect}.sql").write_text(
        _migration_sql(dialect), encoding="utf-8"
    )
    return isolated


def _columns(engine) -> list[str]:
    return [column["name"] for column in inspect(engine).get_columns("supplement_records")]


def _create_production_table(engine) -> None:
    with engine.begin() as conn:
        for statement in PRODUCTION_TABLE:
            conn.execute(text(statement))


def _ledger_rows(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM schema_migrations WHERE id = :id"),
            {"id": MIGRATION_ID},
        ).scalar_one()


def test_pair_documents_guarded_idempotent_drop_and_manual_rollback():
    postgres_sql = _migration_sql("postgresql")
    sqlite_sql = _migration_sql("sqlite")
    statements = _split_sql_statements(postgres_sql)

    assert "ALTER TABLE supplement_records DROP COLUMN IF EXISTS taken_count" in statements
    # A dependent object must stop the drop loudly, never be dropped along with it.
    assert not any("CASCADE" in statement.upper() for statement in statements)
    # The rollback is documented verbatim and never executed by the runner.
    comments = [
        line.strip().lstrip("-").strip()
        for line in postgres_sql.splitlines()
        if line.lstrip().startswith("--")
    ]
    assert ROLLBACK_SQL in comments
    assert not any("ADD COLUMN" in statement.upper() for statement in statements)
    # SQLite schemas come from the ORM, which never mapped the column.
    assert _split_sql_statements(sqlite_sql) == []
    for sql in (postgres_sql, sqlite_sql):
        for line in sql.splitlines():
            if line.lstrip().startswith("--"):
                assert ";" not in line, f"runner splits on semicolons: {line!r}"


def test_sqlite_mirror_is_a_recorded_noop_on_the_orm_schema(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    SupplementRecord.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(insert(SupplementRecord.__table__).values(
            supplement_id=1, user_id=1, record_date=date(2026, 9, 1), taken=True,
        ))
    orm_columns = _columns(engine)
    isolated = _isolated(tmp_path, "sqlite")

    first = apply_managed_migrations(engine, isolated)
    replay = apply_managed_migrations(engine, isolated)

    assert [item.id for item in first.applied] == [MIGRATION_ID]
    assert [item.id for item in replay.skipped] == [MIGRATION_ID]
    assert "taken_count" not in orm_columns
    assert _columns(engine) == orm_columns
    with engine.connect() as conn:
        assert conn.execute(select(SupplementRecord.__table__.c.taken)).scalars().all() == [True]


@requires_postgres
def test_postgres_drop_keeps_rows_indexes_and_orm_io(pg_engine, tmp_path: Path):
    _create_production_table(pg_engine)
    kept = ", ".join(KEPT_COLUMNS)
    with pg_engine.connect() as conn:
        before = conn.execute(text(f"SELECT {kept} FROM supplement_records ORDER BY id")).all()
        assert conn.execute(
            text("SELECT DISTINCT taken_count FROM supplement_records")
        ).scalars().all() == [1]
    isolated = _isolated(tmp_path, "postgresql")

    first = apply_managed_migrations(pg_engine, isolated)
    replay = apply_managed_migrations(pg_engine, isolated)

    assert [item.id for item in first.applied] == [MIGRATION_ID]
    assert [item.id for item in replay.skipped] == [MIGRATION_ID]
    assert _columns(pg_engine) == KEPT_COLUMNS
    inspector = inspect(pg_engine)
    assert {"uq_supprec_supp_date", "idx_supplement_records_user_date"} <= {
        index["name"] for index in inspector.get_indexes("supplement_records")
    }
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("supplement_records")
    } == {"users", "supplement_definitions"}
    with pg_engine.begin() as conn:
        assert conn.execute(
            text(f"SELECT {kept} FROM supplement_records ORDER BY id")
        ).all() == before
        # Bypassing the ledger, the body itself is idempotent.
        for statement in _split_sql_statements(_migration_sql("postgresql")):
            conn.execute(text(statement))
        # The ORM column list still reads and writes the table.
        conn.execute(insert(SupplementRecord.__table__).values(
            supplement_id=3, user_id=1, record_date=date(2026, 9, 2), taken=True,
        ))
        assert len(conn.execute(select(SupplementRecord.__table__)).all()) == 3


@requires_postgres
def test_postgres_drop_is_a_noop_on_an_orm_created_table(pg_engine, tmp_path: Path):
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE supplement_definitions (id SERIAL PRIMARY KEY)"))
    SupplementRecord.__table__.create(pg_engine)
    orm_columns = _columns(pg_engine)

    result = apply_managed_migrations(pg_engine, _isolated(tmp_path, "postgresql"))

    assert [item.id for item in result.applied] == [MIGRATION_ID]
    assert "taken_count" not in orm_columns
    assert _columns(pg_engine) == orm_columns


@requires_postgres
@pytest.mark.parametrize("legacy_value", [0, 2, None])
def test_postgres_refuses_to_drop_a_column_that_carries_information(
    pg_engine, tmp_path: Path, legacy_value,
):
    _create_production_table(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(
            text("UPDATE supplement_records SET taken_count = :value WHERE supplement_id = 2"),
            {"value": legacy_value},
        )

    with pytest.raises(DBAPIError, match="refusing to drop supplement_records.taken_count"):
        apply_managed_migrations(pg_engine, _isolated(tmp_path, "postgresql"))

    assert "taken_count" in _columns(pg_engine)
    assert _ledger_rows(pg_engine) == 0
    with pg_engine.connect() as conn:
        assert conn.execute(
            text("SELECT taken_count FROM supplement_records WHERE supplement_id = 2")
        ).scalar_one() == legacy_value


@requires_postgres
def test_postgres_lock_timeout_fails_fast_without_partial_state(pg_engine, tmp_path: Path):
    _create_production_table(pg_engine)
    isolated = _isolated(tmp_path, "postgresql")
    blocker = pg_engine.connect()
    try:
        # An open transaction that read the table holds ACCESS SHARE until it ends.
        blocker.execute(text("SELECT count(*) FROM supplement_records"))
        started = time.monotonic()
        with pytest.raises(DBAPIError) as caught:
            apply_managed_migrations(pg_engine, isolated)
        elapsed = time.monotonic() - started
    finally:
        blocker.close()

    assert caught.value.orig.pgcode == "55P03"  # lock_not_available
    assert elapsed < 60
    assert "taken_count" in _columns(pg_engine)
    assert _ledger_rows(pg_engine) == 0
    # Roll forward: once the long transaction ends, the same migration applies.
    assert [item.id for item in apply_managed_migrations(pg_engine, isolated).applied] == [
        MIGRATION_ID
    ]


@requires_postgres
def test_postgres_documented_rollback_restores_nullable_default_one(
    pg_engine, tmp_path: Path,
):
    _create_production_table(pg_engine)
    isolated = _isolated(tmp_path, "postgresql")
    apply_managed_migrations(pg_engine, isolated)

    with pg_engine.begin() as conn:
        conn.execute(text(ROLLBACK_SQL))
        conn.execute(text(ROLLBACK_SQL))
        conn.execute(insert(SupplementRecord.__table__).values(
            supplement_id=3, user_id=1, record_date=date(2026, 9, 2),
        ))

    column = next(
        column
        for column in inspect(pg_engine).get_columns("supplement_records")
        if column["name"] == "taken_count"
    )
    assert str(column["type"]) == "INTEGER"
    assert column["nullable"] is True
    assert column["default"] == "1"
    with pg_engine.connect() as conn:
        assert conn.execute(
            text("SELECT DISTINCT taken_count FROM supplement_records")
        ).scalars().all() == [1]
    # The ledger keeps the drop recorded, so the runner never re-drops a restored column.
    assert [item.id for item in apply_managed_migrations(pg_engine, isolated).skipped] == [
        MIGRATION_ID
    ]
    assert "taken_count" in _columns(pg_engine)
