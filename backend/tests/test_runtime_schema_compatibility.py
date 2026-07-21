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
