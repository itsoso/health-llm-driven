from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.services.managed_migrations import apply_managed_migrations


def test_apply_managed_migrations_runs_matching_dialect_once(tmp_path: Path):
    migrations_dir = tmp_path / "managed"
    migrations_dir.mkdir()
    (migrations_dir / "20260516_000001_create_example.sqlite.sql").write_text(
        """
        CREATE TABLE example_items (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE INDEX idx_example_items_name ON example_items(name);
        """,
        encoding="utf-8",
    )
    (migrations_dir / "20260516_000001_create_example.postgresql.sql").write_text(
        "CREATE TABLE should_not_run (id SERIAL PRIMARY KEY);",
        encoding="utf-8",
    )

    engine = create_engine("sqlite:///:memory:")

    first = apply_managed_migrations(engine, migrations_dir)
    second = apply_managed_migrations(engine, migrations_dir)

    tables = inspect(engine).get_table_names()
    assert [m.id for m in first.applied] == ["20260516_000001_create_example"]
    assert second.applied == []
    assert "example_items" in tables
    assert "should_not_run" not in tables
    assert "idx_example_items_name" in [i["name"] for i in inspect(engine).get_indexes("example_items")]

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one()
    assert count == 1


def test_managed_system_knowledge_migration_creates_phase0_tables():
    """验证 KB phase0 migration 在 sqlite 上能正常 CREATE 三张表 + 索引.

    不跑全量 managed_migrations: 其它 ALTER 类 migration (如 add_detected_source)
    假定 ORM 表已建好, 而 ORM create_all 又会把本测试想验证的 kb_* 表先建出来 —
    两难. 直接对 phase0 这份 sqlite 文件跑 SQL 即可.
    """
    engine = create_engine("sqlite:///:memory:")
    migration_file = (
        Path(__file__).resolve().parents[1]
        / "migrations" / "managed"
        / "20260516_200000_create_system_knowledge_tables.sqlite.sql"
    )
    sql = migration_file.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for stmt in sql.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "kb_documents" in tables
    assert "kb_edges" in tables
    assert "kb_audit" in tables
    assert "ix_kb_documents_entity" in [i["name"] for i in inspector.get_indexes("kb_documents")]
    assert "ix_kb_edges_src_relation" in [i["name"] for i in inspector.get_indexes("kb_edges")]


def test_managed_action_cards_graded_at_index_migration(tmp_path: Path):
    """ActionCard graded_at window probes must have a managed partial index."""
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    sqlite_file = migrations_dir / "20260521_121000_add_action_cards_graded_at_index.sqlite.sql"
    postgres_file = migrations_dir / "20260521_121000_add_action_cards_graded_at_index.postgresql.sql"

    assert sqlite_file.exists()
    assert postgres_file.exists()
    assert "WHERE graded_at IS NOT NULL" in postgres_file.read_text(encoding="utf-8")

    isolated_dir = tmp_path / "managed"
    isolated_dir.mkdir()
    (isolated_dir / sqlite_file.name).write_text(sqlite_file.read_text(encoding="utf-8"), encoding="utf-8")

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE action_cards (id INTEGER PRIMARY KEY, graded_at TIMESTAMP)"))

    result = apply_managed_migrations(engine, isolated_dir)

    assert "20260521_121000_add_action_cards_graded_at_index" in [m.id for m in result.applied]
    indexes = inspect(engine).get_indexes("action_cards")
    assert "idx_action_cards_graded_at_not_null" in [i["name"] for i in indexes]


def test_desktop_jobs_has_managed_postgres_migration():
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    postgres_file = migrations_dir / "20260523_120000_create_desktop_jobs.postgresql.sql"

    assert postgres_file.exists()
    sql = postgres_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS desktop_jobs" in sql
    assert "idx_desktop_jobs_user_created" in sql
    assert "idx_desktop_jobs_user_status" in sql
