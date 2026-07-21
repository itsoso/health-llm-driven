#!/usr/bin/env python3
"""Apply new managed migrations before restarting services."""

from pathlib import Path
import os
import sys

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def migration_database_url(*, app_env: str, runtime_url: str) -> str:
    migration_url = os.getenv("MIGRATION_DATABASE_URL", "").strip()
    production = (app_env or "").strip().lower() == "production"
    if production and not migration_url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required in production")
    selected = migration_url or runtime_url
    if production and selected == runtime_url:
        raise RuntimeError("migration and runtime database URLs must use separate roles")
    return selected


def current_database_role(engine) -> str | None:
    if engine.dialect.name != "postgresql":
        return None
    with engine.connect() as connection:
        return str(connection.execute(text("SELECT current_user")).scalar_one())


def validate_migration_role(engine, *, production: bool) -> str | None:
    if not production or engine.dialect.name != "postgresql":
        return current_database_role(engine)
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
            "FROM pg_roles WHERE rolname = current_user"
        )).mappings().one()
    unsafe = [
        field for field in ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole")
        if bool(row[field])
    ]
    if unsafe:
        raise RuntimeError(
            f"migration role {row['rolname']} has forbidden privileges: {', '.join(unsafe)}"
        )
    return str(row["rolname"])


def main() -> int:
    from app.config import settings
    from app.services.managed_migrations import apply_managed_migrations, describe_migrations

    url = migration_database_url(
        app_env=settings.app_env,
        runtime_url=settings.effective_database_url,
    )
    engine = create_engine(url, pool_pre_ping=True)
    migrations_dir = ROOT / "migrations" / "managed"
    try:
        production = (settings.app_env or "").strip().lower() == "production"
        migration_role = validate_migration_role(
            engine,
            production=production,
        )
        if production:
            runtime_engine = create_engine(settings.effective_database_url, pool_pre_ping=True)
            try:
                runtime_role = current_database_role(runtime_engine)
            finally:
                runtime_engine.dispose()
            if migration_role == runtime_role:
                raise RuntimeError("migration and runtime database roles must differ")
        result = apply_managed_migrations(engine, migrations_dir)
        print(f"managed migrations applied: {describe_migrations(result.applied)}")
        print(f"managed migrations skipped: {describe_migrations(result.skipped)}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
