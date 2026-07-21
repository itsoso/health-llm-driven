#!/usr/bin/env python3
"""Verify that the checked-out runtime can read and write its declared schema."""

from __future__ import annotations

import importlib
import pkgutil

from sqlalchemy import false, inspect, select, update


def verify_runtime_schema_compatibility(*, engine, metadata, session_factory) -> int:
    inspector = inspect(engine)
    missing_tables: list[str] = []
    missing_columns: list[str] = []

    for table in metadata.sorted_tables:
        if not inspector.has_table(table.name, schema=table.schema):
            missing_tables.append(table.fullname)
            continue
        actual_columns = {
            column["name"]
            for column in inspector.get_columns(table.name, schema=table.schema)
        }
        for column in table.columns:
            if column.name not in actual_columns:
                missing_columns.append(f"{table.fullname}.{column.name}")

    if missing_tables:
        raise RuntimeError(f"missing tables: {', '.join(sorted(missing_tables))}")
    if missing_columns:
        raise RuntimeError(f"missing columns: {', '.join(sorted(missing_columns))}")

    checked = 0
    session = session_factory()
    try:
        for table in metadata.sorted_tables:
            session.execute(select(table).limit(0))
            writable = next(
                (column for column in table.columns if column.computed is None),
                None,
            )
            if writable is not None:
                session.execute(
                    update(table)
                    .where(false())
                    .values({writable.name: writable})
                )
            checked += 1
        session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return checked


def _import_all_models() -> None:
    import app.models as models_package

    for module in pkgutil.iter_modules(models_package.__path__):
        importlib.import_module(f"app.models.{module.name}")


def main() -> None:
    _import_all_models()
    from app.database import Base, SessionLocal, engine

    checked = verify_runtime_schema_compatibility(
        engine=engine,
        metadata=Base.metadata,
        session_factory=SessionLocal,
    )
    print(f"ROLLBACK_SCHEMA_PROBE_OK tables={checked}")


if __name__ == "__main__":
    main()
