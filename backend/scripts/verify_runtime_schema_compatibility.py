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
    relaxed_nonnullable_columns: list[tuple[object, object]] = []

    for table in metadata.sorted_tables:
        if not inspector.has_table(table.name, schema=table.schema):
            missing_tables.append(table.fullname)
            continue
        actual_columns = {
            column["name"]: column
            for column in inspector.get_columns(table.name, schema=table.schema)
        }
        for column in table.columns:
            if column.name not in actual_columns:
                missing_columns.append(f"{table.fullname}.{column.name}")
            elif (
                column.nullable is False
                and actual_columns[column.name].get("nullable") is True
            ):
                relaxed_nonnullable_columns.append((table, column))

    if missing_tables:
        raise RuntimeError(f"missing tables: {', '.join(sorted(missing_tables))}")
    if missing_columns:
        raise RuntimeError(f"missing columns: {', '.join(sorted(missing_columns))}")

    checked = 0
    session = session_factory()
    try:
        incompatible_nulls = [
            f"{table.fullname}.{column.name}"
            for table, column in relaxed_nonnullable_columns
            if session.execute(
                select(column).where(column.is_(None)).limit(1)
            ).first()
            is not None
        ]
        if incompatible_nulls:
            raise RuntimeError(
                "non-null runtime contract violated: "
                + ", ".join(sorted(incompatible_nulls))
            )
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
