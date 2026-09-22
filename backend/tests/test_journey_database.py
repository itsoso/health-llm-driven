"""Managed migration replay and PostgreSQL-authoritative journey semantics."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.test_journey import journey_data, body, save


@pytest.fixture
def pg(db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL production semantics")
    return db


def test_journey_migration_pair_replay(tmp_path):
    from app.services.managed_migrations import apply_managed_migrations
    migrations = Path(__file__).resolve().parents[1] / "migrations" / "managed"
    isolated = tmp_path / "managed"; isolated.mkdir()
    for dialect in ("postgresql", "sqlite"):
        path = migrations / f"20260922_190000_monthly_journey.{dialect}.sql"
        sql = path.read_text()
        for fragment in ("ON DELETE CASCADE", "ck_journey_one_source", "uq_journey_owner_chat", "ix_journey_owner_date_id", "REFERENCES agent_messages(id)"):
            assert fragment in sql
        (isolated / path.name).write_text(sql)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        for table in ("users", "diet_records", "health_episodes", "agent_messages"):
            connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)"))
    first = apply_managed_migrations(engine, isolated)
    assert [item.id for item in first.applied] == ["20260922_190000_monthly_journey"]
    assert apply_managed_migrations(engine, isolated).applied == []
    inspector = inspect(engine)
    assert {c["name"] for c in inspector.get_columns("journey_places")} == {"id","user_id","diet_record_id","life_event_id","chat_message_id","city","local_date","timezone","location_source","version","created_at","updated_at"}
    assert len(inspector.get_foreign_keys("journey_places")) == 4
    engine.dispose()


def test_journey_pg_migration_replay_constraints_and_index(pg, tmp_path):
    from app.services.managed_migrations import apply_managed_migrations
    # Empty feature table only, in the explicitly synthetic disposable test DB.
    if inspect(pg.get_bind()).has_table("schema_migrations"):
        # The shared db fixture recreates ORM tables but this runner-owned
        # bookkeeping table is intentionally outside Base.metadata.
        pg.execute(text("DELETE FROM schema_migrations WHERE id=:id"), {"id":"20260922_190000_monthly_journey"})
    pg.execute(text("DROP TABLE journey_places")); pg.commit()
    path = Path(__file__).resolve().parents[1] / "migrations/managed/20260922_190000_monthly_journey.postgresql.sql"
    (tmp_path / path.name).write_text(path.read_text())
    assert len(apply_managed_migrations(pg.get_bind(), tmp_path).applied) == 1
    assert apply_managed_migrations(pg.get_bind(), tmp_path).applied == []
    names = {c["name"] for c in inspect(pg.get_bind()).get_check_constraints("journey_places")}
    assert names == {"ck_journey_one_source", "ck_journey_version", "ck_journey_location_source"}
    pg.execute(text("SET LOCAL enable_seqscan = off"))
    plan = pg.execute(text("EXPLAIN SELECT id FROM journey_places WHERE user_id=1 AND local_date >= '2026-09-01' AND local_date < '2026-10-01' ORDER BY local_date,id")).all()
    assert "ix_journey_owner_date_id" in str(plan)
    pg.rollback()


@pytest.mark.parametrize("invalid", [{}, {"diet_record_id": "diet", "life_event_id":"event"}, {"version":0,"diet_record_id":"diet"}, {"location_source":"always","diet_record_id":"diet"}])
def test_pg_exactly_one_source_and_value_constraints(pg, journey_data, invalid):
    from app.models.journey_place import JourneyPlace
    user, _, diet, _, _, event = journey_data
    values = {"user_id": user.id, "city":"成都", "local_date":diet.record_date, "timezone":"Asia/Shanghai", "location_source":"manual", "version":1}
    values.update({key: diet.id if value == "diet" else event.id if value == "event" else value for key,value in invalid.items()})
    with pytest.raises(IntegrityError):
        pg.add(JourneyPlace(**values)); pg.flush()
    pg.rollback()


def test_pg_parallel_create_and_update_are_not_last_write_wins(pg, journey_data):
    from app.services.journey import put_place
    from app.schemas.journey import JourneyWrite
    from app.models.journey_place import JourneyPlace
    user, _, diet, *_ = journey_data
    owner, source_id, engine = user.id, diet.id, pg.get_bind()
    pg.commit()
    def race(expected_version):
        barrier = Barrier(2)
        def attempt(city):
            with Session(engine) as session:
                payload = body(); payload.update(city=city, expected_version=expected_version)
                barrier.wait(timeout=10)
                try:
                    result = put_place(session, owner, "diet", source_id, JourneyWrite.model_validate(payload))
                    return result["version"]
                except HTTPException as error:
                    session.rollback()
                    return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ["成都","北京"]))
        assert sorted(results) == [expected_version + 1, 409]
    race(0); race(1)
    assert pg.query(JourneyPlace).one().version == 2


@pytest.mark.parametrize("kind,index,table", [("diet",2,"diet_records"),("chat_photo",4,"agent_messages"),("life_event",5,"health_episodes")])
def test_pg_source_cascade_does_not_affect_other_owner(client, pg, journey_data, kind, index, table):
    from app.models.journey_place import JourneyPlace
    from app.schemas.journey import JourneyWrite
    from app.services.journey import put_place
    user, headers, _, foreign, *_ = journey_data
    source_id = journey_data[index].id
    own = put_place(pg, user.id, kind, source_id, JourneyWrite.model_validate(body()))
    other = put_place(pg, foreign.user_id, "diet", foreign.id, JourneyWrite.model_validate(body()))
    pg.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id":source_id}); pg.commit()
    assert pg.get(JourneyPlace, own["id"]) is None
    assert pg.get(JourneyPlace, other["id"]) is not None
    response = client.post("/api/v1/journey/export-preview", headers=headers, json={"items":[{"place_id":own["id"],"version":1,"image_keys":[]}]})
    assert response.status_code == 404


def test_pg_account_cascade_fk_and_deletion_inventory(pg, journey_data):
    from app.models.journey_place import JourneyPlace
    from app.services.account_deletion import _row_counts
    from app.schemas.journey import JourneyWrite
    from app.services.journey import put_place
    user, _, diet, *_ = journey_data
    put_place(pg, user.id, "diet", diet.id, JourneyWrite.model_validate(body()))
    report = _row_counts(pg, "journey_places", user.id)
    assert report["blocking_rows"] == 1
    fks = inspect(pg.get_bind()).get_foreign_keys("journey_places")
    owner_fk = next(fk for fk in fks if fk["constrained_columns"] == ["user_id"])
    assert owner_fk["referred_table"] == "users" and owner_fk["options"]["ondelete"] == "CASCADE"
    # Check source cleanup used by account erasure as well as the independently
    # declared user FK; this does not claim all legacy account erasure works.
    pg.execute(text("DELETE FROM diet_records WHERE user_id=:id"), {"id":user.id})
    pg.commit()
    assert pg.query(JourneyPlace).filter_by(user_id=user.id).count() == 0
