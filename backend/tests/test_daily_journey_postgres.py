"""Managed schema and real PostgreSQL races for explicitly opted-in GPS capture."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.services.managed_migrations import apply_managed_migrations
from app.services import daily_journey as service
from app.models.agent_audit_log import AgentAuditLog
from app.models.daily_journey import (
    DailyJourneySession,
    DailyJourneyPoint,
    DailyJourneyRequest,
)
from app.schemas.daily_journey import JourneyStart, JourneyStateChange, JourneyBatch

MIGRATION = "20261018_120000_daily_journeys"
URL = os.getenv("TEST_DATABASE_URL")
IS_PG = bool(URL and make_url(URL).get_backend_name() == "postgresql")
NOW = datetime(2026, 10, 18, 3, tzinfo=timezone.utc)


def install(engine, tmp_path, dialect):
    directory = tmp_path / dialect
    directory.mkdir()
    src = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "managed"
        / f"{MIGRATION}.{dialect}.sql"
    )
    (directory / src.name).write_text(src.read_text())
    first = apply_managed_migrations(engine, directory)
    again = apply_managed_migrations(engine, directory)
    assert [m.id for m in first.applied] == [MIGRATION]
    assert [m.id for m in again.skipped] == [MIGRATION]


def test_daily_journey_sqlite_migration_mirror(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    install(engine, tmp_path, "sqlite")
    assert {
        "daily_journey_sessions",
        "daily_journey_points",
        "daily_journey_requests",
    } <= set(inspect(engine).get_table_names())
    assert set(DailyJourneyRequest.__table__.c.keys()) == {
        "user_id",
        "request_id",
        "session_id",
    }
    assert any(
        i["name"] == "uq_daily_journey_unfinished_owner" and i["unique"]
        for i in inspect(engine).get_indexes("daily_journey_sessions")
    )
    engine.dispose()


@pytest.fixture
def pg(tmp_path, monkeypatch):
    if not IS_PG:
        pytest.skip("requires TEST_DATABASE_URL PostgreSQL")
    schema = "daily_journey_" + uuid4().hex
    admin = create_engine(URL)
    engine = None
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(URL, connect_args={"options": f"-csearch_path={schema}"})
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            conn.execute(text("INSERT INTO users (id) VALUES (1),(2)"))
        install(engine, tmp_path, "postgresql")
        AgentAuditLog.__table__.create(engine)
        clock = [NOW]
        monkeypatch.setattr(service, "utcnow", lambda: clock[0])
        yield engine, sessionmaker(bind=engine), clock
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def request():
    return JourneyStart(
        request_id=uuid4(),
        client_id=uuid4(),
        timezone="Asia/Shanghai",
        retention_days=1,
        consent=True,
    )


def test_postgres_start_race_and_active_unique_constraint(pg):
    engine, factory, clock = pg
    barrier = Barrier(2)

    def concurrent_start(_):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                return service.start_session(db, 1, request())["id"]
            except HTTPException as error:
                db.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(concurrent_start, range(2)))
    assert sum(isinstance(value, str) for value in results) == 1 and 409 in results
    with factory() as db:
        row = db.query(DailyJourneySession).one()
        values = {
            column.name: getattr(row, column.name) for column in row.__table__.columns
        }
        values["id"] = str(uuid4())
        db.add(DailyJourneySession(**values))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_postgres_state_cas_and_duplicate_upload_races(pg):
    engine, factory, clock = pg
    req = request()
    with factory() as db:
        session = service.start_session(db, 1, req)
    sample = {
        "id": str(uuid4()),
        "recorded_at": NOW.isoformat(),
        "latitude": 31.2,
        "longitude": 121.4,
        "accuracy_m": 5.0,
    }
    batch = JourneyBatch(client_id=req.client_id, segment=1, points=[sample])
    barrier = Barrier(2)

    def upload(_):
        with factory() as db:
            barrier.wait(timeout=10)
            return service.upload_points(db, 1, session["id"], batch)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(upload, range(2)))
    assert (
        sum(r["accepted"] for r in results) == 1
        and sum(r["duplicate"] for r in results) == 1
    )
    barrier = Barrier(2)

    def pause(index):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                return service.change_state(
                    db,
                    1,
                    session["id"],
                    JourneyStateChange(
                        action=("pause", "end")[index],
                        expected_version=1,
                        client_id=req.client_id,
                    ),
                )["version"]
            except HTTPException as error:
                db.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pause, range(2)))
    assert sorted(results) == [2, 409]
    with factory() as db:
        row = db.query(DailyJourneySession).one()
        assert row.point_count == 1 and row.status in ("paused", "ended")
        raw = db.execute(text("SELECT payload FROM daily_journey_points")).scalar()
        assert raw.startswith("gAAAA") and "31.2" not in raw
        assert row.started_at.tzinfo is not None and row.started_at == NOW


def test_postgres_delete_purge_and_account_cascade(pg):
    engine, factory, clock = pg
    req = request()
    with factory() as db:
        session = service.start_session(db, 1, req)
        batch = JourneyBatch(
            client_id=req.client_id,
            segment=1,
            points=[
                {
                    "id": uuid4(),
                    "recorded_at": NOW,
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "accuracy_m": 3.0,
                }
            ],
        )
        service.upload_points(db, 1, session["id"], batch)
        clock[0] = session["expires_at"]
        with pytest.raises(HTTPException):
            service.review_session(db, 1, session["id"])
        db.rollback()
        assert service.purge_expired(db) == 1
        assert (
            db.query(DailyJourneyPoint).count()
            == db.query(DailyJourneySession).count()
            == 0
        )
        assert db.query(DailyJourneyRequest).count() == 1
        with pytest.raises(HTTPException) as error:
            service.start_session(db, 1, req)
        assert error.value.status_code == 410
        db.rollback()
        db.execute(text("DELETE FROM users WHERE id=1"))
        db.commit()
        assert db.query(DailyJourneyRequest).count() == 0


def test_postgres_account_delete_removes_active_payload_and_replay_barrier(pg):
    engine, factory, clock = pg
    req = request()
    with factory() as db:
        session = service.start_session(db, 2, req)
        batch = JourneyBatch(
            client_id=req.client_id,
            segment=1,
            points=[
                {
                    "id": uuid4(),
                    "recorded_at": NOW,
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "accuracy_m": 3.0,
                }
            ],
        )
        service.upload_points(db, 2, session["id"], batch)
        db.execute(text("DELETE FROM users WHERE id=2"))
        db.commit()
        assert db.query(DailyJourneySession).count() == 0
        assert db.query(DailyJourneyPoint).count() == 0
        assert db.query(DailyJourneyRequest).count() == 0


def test_postgres_upload_delete_race_cannot_resurrect(pg):
    engine, factory, clock = pg
    req = request()
    with factory() as db:
        session = service.start_session(db, 1, req)
    batch = JourneyBatch(
        client_id=req.client_id,
        segment=1,
        points=[
            {
                "id": uuid4(),
                "recorded_at": NOW,
                "latitude": 1.0,
                "longitude": 2.0,
                "accuracy_m": 3.0,
            }
        ],
    )
    barrier = Barrier(2)

    def operation(index):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                if index:
                    service.delete_session(db, 1, session["id"])
                    return 204
                return service.upload_points(db, 1, session["id"], batch)["accepted"]
            except HTTPException as error:
                db.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(operation, range(2)))
    assert results[1] == 204 and results[0] in (1, 404)
    with factory() as db:
        assert db.query(DailyJourneySession).count() == 0
        assert db.query(DailyJourneyPoint).count() == 0
        with pytest.raises(HTTPException) as error:
            service.start_session(db, 1, req)
        assert error.value.status_code == 410
