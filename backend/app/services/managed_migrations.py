"""Small managed migration runner for new production migrations.

Historical migrations in this repository are mixed raw SQL, one-off scripts,
and SQLite compatibility files. This runner intentionally scopes itself to the
`migrations/managed` directory so new schema changes have an explicit,
idempotent deployment path without replaying old migrations on production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from sqlalchemy import Engine, text


SCHEMA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id VARCHAR(200) PRIMARY KEY,
    checksum VARCHAR(64) NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


@dataclass(frozen=True)
class ManagedMigration:
    id: str
    path: Path
    checksum: str


@dataclass
class MigrationRunResult:
    applied: list[ManagedMigration] = field(default_factory=list)
    skipped: list[ManagedMigration] = field(default_factory=list)


def _migration_id(path: Path) -> str:
    name = path.name
    for suffix in (".postgresql.sql", ".sqlite.sql", ".sql"):
        if name.endswith(suffix):
            return name.removesuffix(suffix)
    return path.stem


def _migration_dialect(path: Path) -> str | None:
    name = path.name
    if name.endswith(".postgresql.sql"):
        return "postgresql"
    if name.endswith(".sqlite.sql"):
        return "sqlite"
    return None


def _read_migrations(migrations_dir: Path, dialect_name: str) -> list[ManagedMigration]:
    if not migrations_dir.exists():
        return []

    chosen: dict[str, Path] = {}
    for path in sorted(migrations_dir.glob("*.sql")):
        if ".down." in path.name:
            continue
        dialect = _migration_dialect(path)
        if dialect is not None and dialect != dialect_name:
            continue
        migration_id = _migration_id(path)
        current = chosen.get(migration_id)
        if current is None:
            chosen[migration_id] = path
            continue
        # Prefer a dialect-specific file over a generic file.
        if _migration_dialect(current) is None and dialect == dialect_name:
            chosen[migration_id] = path

    migrations = []
    for migration_id, path in sorted(chosen.items()):
        body = path.read_text(encoding="utf-8")
        migrations.append(ManagedMigration(migration_id, path, sha256(body.encode("utf-8")).hexdigest()))
    return migrations


def _applied_checksums(engine: Engine) -> dict[str, str]:
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_TABLE_SQL))
        rows = conn.execute(text("SELECT id, checksum FROM schema_migrations")).fetchall()
    return {row[0]: row[1] for row in rows}


def _split_sql_statements(sql: str) -> list[str]:
    return [part.strip() for part in sql.split(";") if part.strip()]


def apply_managed_migrations(engine: Engine, migrations_dir: str | Path) -> MigrationRunResult:
    """Apply pending migrations from a managed directory.

    The runner is intentionally strict: if an already-applied migration has a
    different checksum, it raises instead of silently continuing.
    """

    migrations_path = Path(migrations_dir)
    dialect_name = engine.dialect.name
    migrations = _read_migrations(migrations_path, dialect_name)
    applied = _applied_checksums(engine)
    result = MigrationRunResult()

    for migration in migrations:
        old_checksum = applied.get(migration.id)
        if old_checksum:
            if old_checksum != migration.checksum:
                raise RuntimeError(
                    f"Managed migration checksum changed: {migration.id}. "
                    "Create a new migration instead of editing an applied one."
                )
            result.skipped.append(migration)
            continue

        sql = migration.path.read_text(encoding="utf-8")
        with engine.begin() as conn:
            for statement in _split_sql_statements(sql):
                conn.execute(text(statement))
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (id, checksum) "
                    "VALUES (:id, :checksum)"
                ),
                {"id": migration.id, "checksum": migration.checksum},
            )
        result.applied.append(migration)

    return result


def describe_migrations(migrations: Iterable[ManagedMigration]) -> str:
    return ", ".join(m.id for m in migrations) or "none"
