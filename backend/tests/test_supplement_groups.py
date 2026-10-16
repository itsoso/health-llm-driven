"""Synthetic supplement group ownership, snapshots and atomicity."""

from datetime import timedelta
import pytest
from app.models.user import User
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.health_protocol import HealthProtocolEvent
from app.services import health_protocol_service as protocols
from app.services import supplement_groups as groups


@pytest.fixture
def owner(db):
    u = User(
        username="group-test",
        email="group@example.test",
        hashed_password="test",
        name="Synthetic user",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.flush()
    a = SupplementDefinition(user_id=u.id, name="Synthetic A", dosage="reference only")
    b = SupplementDefinition(user_id=u.id, name="Synthetic B")
    db.add_all([a, b])
    db.commit()
    return u.id, [a.id, b.id]


def test_snapshot_replay_preserves_dose_and_original_members(db, owner):
    uid, ids = owner
    g = groups.save_group(db, uid, "Morning", ids)
    today = groups.list_groups(db, uid)["record_date"]
    db.add(
        SupplementRecord(
            user_id=uid,
            supplement_id=ids[0],
            record_date=today,
            taken=True,
            actual_dosage="prior",
        )
    )
    db.commit()
    receipt = groups.confirm_group(db, uid, g["id"], g["revision"], today)
    assert len(receipt["members"]) == 2
    assert (
        db.query(SupplementRecord).filter_by(supplement_id=ids[0]).one().actual_dosage
        == "prior"
    )
    assert (
        db.query(SupplementRecord).filter_by(supplement_id=ids[1]).one().actual_dosage
        is None
    )
    changed = groups.save_group(db, uid, "Other", [ids[0]], g["id"], g["revision"])
    assert groups.confirm_group(db, uid, g["id"], changed["revision"], today) == receipt
    assert db.query(HealthProtocolEvent).count() == 1


@pytest.mark.parametrize(
    "operation",
    [
        "complete_protocol",
        "skip_protocol",
        "snooze_protocol",
        "resume_protocol",
        "auto_observe_protocol",
        "archive_protocol",
    ],
)
def test_generic_writes_blocked(db, owner, operation):
    uid, ids = owner
    g = groups.save_group(db, uid, "Morning", ids)
    with pytest.raises(ValueError):
        getattr(protocols, operation)(db, g["id"], uid)
    assert protocols.list_protocols(db, uid) == []
    assert protocols.today_status(db, uid) == []
    assert db.query(HealthProtocolEvent).count() == 0


def test_changes_date_ownership_and_generic_creation_rejected(db, owner):
    uid, ids = owner
    g = groups.save_group(db, uid, "Morning", ids)
    with pytest.raises(ValueError):
        protocols.create_protocol(
            db,
            uid,
            {
                "domain": "supplement",
                "name": "Fake",
                "source_model": "supplement_group",
            },
        )
    with pytest.raises(ValueError):
        groups.save_group(db, uid + 999, "Other", ids)
    with pytest.raises(ValueError):
        groups.confirm_group(
            db,
            uid,
            g["id"],
            g["revision"],
            groups.list_groups(db, uid)["record_date"] - timedelta(days=1),
        )
    db.query(SupplementDefinition).filter_by(id=ids[0]).update({"dosage": "changed"})
    db.commit()
    with pytest.raises(ValueError):
        groups.confirm_group(
            db, uid, g["id"], g["revision"], groups.list_groups(db, uid)["record_date"]
        )
    assert db.query(SupplementRecord).count() == 0


def test_api_auth_validation_and_save_does_not_checkin(client, db, owner):
    from app.services.auth import auth_service

    uid, ids = owner
    headers = {
        "Authorization": "Bearer " + auth_service.create_access_token({"sub": str(uid)})
    }
    assert client.get("/api/v1/supplements/groups").status_code == 401
    assert (
        client.post(
            "/api/v1/supplements/groups",
            headers=headers,
            json={"name": "Morning", "supplement_ids": ids, "user_id": uid},
        ).status_code
        == 422
    )
    r = client.post(
        "/api/v1/supplements/groups",
        headers=headers,
        json={"name": "Morning", "supplement_ids": ids},
    )
    assert r.status_code == 200
    g = r.json()
    assert db.query(SupplementRecord).count() == 0
    assert db.query(HealthProtocolEvent).count() == 0
    day = client.get("/api/v1/supplements/groups", headers=headers).json()[
        "record_date"
    ]
    assert (
        client.post(
            f"/api/v1/supplements/groups/{g['id']}/confirm",
            headers=headers,
            json={"revision": g["revision"], "record_date": day, "confirmed": False},
        ).status_code
        == 422
    )
    r = client.post(
        f"/api/v1/supplements/groups/{g['id']}/confirm",
        headers=headers,
        json={"revision": g["revision"], "record_date": day, "confirmed": True},
    )
    assert r.status_code == 200
    assert r.json()["source"] == "manual_group"


def test_cross_owner_group_and_inactive_members_rejected(db, owner):
    uid, ids = owner
    other = User(
        username="other-group",
        email="other-group@example.test",
        hashed_password="test",
        name="Other",
    )
    db.add(other)
    db.commit()
    g = groups.save_group(db, uid, "Morning", ids)
    with pytest.raises(ValueError):
        groups.save_group(db, other.id, "Stolen", ids)
    with pytest.raises(ValueError):
        groups.confirm_group(
            db,
            other.id,
            g["id"],
            g["revision"],
            groups.list_groups(db, uid)["record_date"],
        )
    db.query(SupplementDefinition).filter_by(id=ids[0]).update({"is_active": False})
    db.commit()
    fresh = groups.list_groups(db, uid)["groups"][0]
    assert not fresh["members"][0]["available"]
    with pytest.raises(ValueError):
        groups.confirm_group(
            db,
            uid,
            g["id"],
            fresh["revision"],
            groups.list_groups(db, uid)["record_date"],
        )
    assert db.query(SupplementRecord).count() == 0


def test_group_snapshot_survives_definition_delete_and_archive(db, owner):
    uid, ids = owner
    g = groups.save_group(db, uid, "Morning", ids)
    day = groups.list_groups(db, uid)["record_date"]
    receipt = groups.confirm_group(db, uid, g["id"], g["revision"], day)
    db.delete(db.get(SupplementDefinition, ids[0]))
    db.commit()
    fresh = groups.list_groups(db, uid)["groups"][0]
    assert fresh["today_confirmation"] == receipt
    assert not fresh["members"][0]["available"]
    groups.archive_group(db, uid, g["id"], fresh["revision"])
    assert groups.list_groups(db, uid)["groups"] == []
    assert db.query(HealthProtocolEvent).one().value == receipt


def test_failure_mid_batch_rolls_back_every_record_and_event(db, owner):
    from sqlalchemy import event

    uid, ids = owner
    g = groups.save_group(db, uid, "Morning", ids)
    day = groups.list_groups(db, uid)["record_date"]

    def fail_second(mapper, connection, target):
        if target.supplement_id == ids[1]:
            connection.execute(
                SupplementRecord.__table__.insert().values(
                    user_id=uid, supplement_id=ids[1], record_date=day, taken=True
                )
            )

    event.listen(SupplementRecord, "before_insert", fail_second)
    try:
        with pytest.raises(ValueError, match="并发变化"):
            groups.confirm_group(db, uid, g["id"], g["revision"], day)
    finally:
        event.remove(SupplementRecord, "before_insert", fail_second)
    assert db.query(SupplementRecord).count() == 0
    assert db.query(HealthProtocolEvent).count() == 0


def test_generic_adjustment_and_direct_adapter_reject_group(db, owner):
    uid, ids = owner
    g = groups.save_group(db, uid, "Morning", ids)
    with pytest.raises(ValueError):
        protocols.apply_adjustment(db, g["id"], uid, "time_window", "morning")


def test_postgres_concurrent_confirmations_return_one_snapshot(db, owner):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locks and JSONB")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session

    uid, ids = owner
    g = groups.save_group(db, uid, "Morning", ids)
    day = groups.list_groups(db, uid)["record_date"]
    db.rollback()
    barrier = Barrier(2)

    def submit():
        with Session(db.bind) as session:
            barrier.wait(timeout=10)
            return groups.confirm_group(session, uid, g["id"], g["revision"], day)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        results = [f.result(timeout=20) for f in futures]
    assert results[0] == results[1]
    assert db.query(SupplementRecord).count() == 2
    assert db.query(HealthProtocolEvent).count() == 1


def test_forged_voice_projection_is_not_actionable():
    from app.services.agenda_service import _is_voice_actionable

    assert not _is_voice_actionable(
        {
            "source": {"object_type": "health_protocol"},
            "status": "pending",
            "type": "hydration",
            "source_model": "supplement_group",
        }
    )


@pytest.mark.parametrize("bad_ids", [[True], [1.0], ["1"], [0], [-1], [1, 1], []])
def test_strict_member_identifiers(bad_ids):
    from app.schemas.supplement_groups import SupplementGroupCreate

    with pytest.raises(ValueError):
        SupplementGroupCreate(name="Morning", supplement_ids=bad_ids)


@pytest.mark.parametrize("bad_confirmation", [False, 1, "true", None])
def test_explicit_boolean_confirmation_only(bad_confirmation):
    from app.schemas.supplement_groups import SupplementGroupConfirm

    with pytest.raises(ValueError):
        SupplementGroupConfirm(
            revision="x", record_date="2026-10-16", confirmed=bad_confirmation
        )


def test_group_list_has_bounded_queries(db, owner):
    from sqlalchemy import event

    uid, ids = owner
    for i in range(5):
        groups.save_group(db, uid, f"Group {i}", ids)
    queries = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", count)
    try:
        result = groups.list_groups(db, uid)
    finally:
        event.remove(db.bind, "before_cursor_execute", count)
    assert len(result["groups"]) == 5
    assert len(queries) == 4


def test_account_timezone_controls_confirm_date(db, owner, monkeypatch):
    from datetime import datetime, timezone
    from app.models.user_profile import UserProfile

    uid, ids = owner
    db.add(UserProfile(user_id=uid, manual_timezone="America/Los_Angeles"))
    db.commit()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 16, 2, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(groups, "datetime", Clock)
    g = groups.save_group(db, uid, "Morning", ids)
    state = groups.list_groups(db, uid)
    assert state["record_date"].isoformat() == "2026-10-15"
    assert state["timezone"] == "America/Los_Angeles"
    receipt = groups.confirm_group(
        db, uid, g["id"], g["revision"], state["record_date"]
    )
    assert receipt["record_date"] == "2026-10-15"


def test_generic_archive_group_returns_explicit_client_error(client, db, owner):
    from app.services.auth import auth_service

    uid, ids = owner
    group = groups.save_group(db, uid, "Morning", ids)
    headers = {
        "Authorization": "Bearer " + auth_service.create_access_token({"sub": str(uid)})
    }
    response = client.post(f"/api/v1/protocols/{group['id']}/archive", headers=headers)
    assert response.status_code == 400
    assert "专用确认入口" in response.json()["detail"]
    assert len(groups.list_groups(db, uid)["groups"]) == 1
    assert db.query(HealthProtocolEvent).count() == 0
