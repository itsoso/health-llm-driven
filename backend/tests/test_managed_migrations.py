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
