import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from scripts.verify_runtime_schema_compatibility import (
    verify_runtime_schema_compatibility,
)


ProbeBase = declarative_base()


class ProbeRecord(ProbeBase):
    __tablename__ = "probe_records"

    id = Column(Integer, primary_key=True)
    value = Column(String(20), nullable=False)


def test_runtime_model_bootstrap_registers_bowel_timer():
    backend_root = Path(__file__).resolve().parents[1]
    code = """
from app.database import Base
from scripts.verify_runtime_schema_compatibility import _import_all_models
_import_all_models()
raise SystemExit(0 if "bowel_timers" in Base.metadata.tables else 1)
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend_root,
        env={
            **os.environ,
            "DATABASE_URL": "sqlite:///:memory:",
            "SKIP_DB_INIT": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_runtime_schema_probe_checks_declared_reads_and_zero_row_writes():
    engine = create_engine("sqlite:///:memory:")
    ProbeBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    checked = verify_runtime_schema_compatibility(
        engine=engine,
        metadata=ProbeBase.metadata,
        session_factory=factory,
    )

    assert checked == 1


def test_runtime_schema_probe_fails_when_old_code_table_is_missing():
    engine = create_engine("sqlite:///:memory:")
    ProbeBase.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE probe_records"))
    factory = sessionmaker(bind=engine)

    with pytest.raises(RuntimeError, match="missing tables"):
        verify_runtime_schema_compatibility(
            engine=engine,
            metadata=ProbeBase.metadata,
            session_factory=factory,
        )


def test_runtime_schema_probe_fails_when_declared_column_is_missing():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE probe_records (id INTEGER PRIMARY KEY)"
        ))
    factory = sessionmaker(bind=engine)

    with pytest.raises(
        RuntimeError,
        match=r"missing columns: probe_records\.value",
    ):
        verify_runtime_schema_compatibility(
            engine=engine,
            metadata=ProbeBase.metadata,
            session_factory=factory,
        )


def test_runtime_schema_probe_blocks_old_nonnullable_model_when_live_rows_are_null():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE probe_records (id INTEGER PRIMARY KEY, value VARCHAR(20))"
        ))
        connection.execute(text(
            "INSERT INTO probe_records (id, value) VALUES (1, NULL)"
        ))
    factory = sessionmaker(bind=engine)

    with pytest.raises(
        RuntimeError,
        match=r"non-null runtime contract violated: probe_records\.value",
    ):
        verify_runtime_schema_compatibility(
            engine=engine,
            metadata=ProbeBase.metadata,
            session_factory=factory,
        )


def test_runtime_schema_probe_fails_when_bowel_timer_table_is_missing():
    from app.database import Base

    engine = create_engine("sqlite:///:memory:")
    tables_without_bowel_timer = [
        table for table in Base.metadata.sorted_tables if table.name != "bowel_timers"
    ]
    Base.metadata.create_all(engine, tables=tables_without_bowel_timer)
    factory = sessionmaker(bind=engine)

    with pytest.raises(RuntimeError, match="bowel_timers"):
        verify_runtime_schema_compatibility(
            engine=engine,
            metadata=Base.metadata,
            session_factory=factory,
        )


def test_runtime_schema_probe_accepts_current_application_schema(db):
    from app.database import Base

    engine = db.get_bind()
    factory = sessionmaker(bind=engine)

    checked = verify_runtime_schema_compatibility(
        engine=engine,
        metadata=Base.metadata,
        session_factory=factory,
    )

    assert checked == len(Base.metadata.tables)
