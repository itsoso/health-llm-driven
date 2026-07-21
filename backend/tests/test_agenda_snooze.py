"""Agenda 稍后/恢复合同：持久、可逆、用户隔离且不伪造完成。"""
from datetime import UTC, date, datetime, timedelta
import uuid

import pytest
from sqlalchemy import update

from app.models.health_protocol import HealthProtocolEvent
from app.models.user import User
from app.services import health_protocol_service as proto_svc
from app.services.auth import auth_service


def _user_and_headers(db):
    user = User(
        username=f"agenda_snooze_{uuid.uuid4().hex[:8]}",
        email=f"agenda_snooze_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="agenda-snooze",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, {"Authorization": f"Bearer {token}"}


def test_agenda_snooze_persists_and_projects_until(client, db):
    user, headers = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)

    response = client.post(
        "/api/v1/agenda/snooze",
        headers=headers,
        json={"object_type": "health_protocol", "object_id": protocol.id, "minutes": 30},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "snoozed"
    assert body["minutes"] == 30
    assert datetime.fromisoformat(body["snoozed_until"].replace("Z", "+00:00"))

    item = next(
        item for item in client.get("/api/v1/agenda/today", headers=headers).json()["items"]
        if item["source"] == {"object_type": "health_protocol", "object_id": protocol.id}
    )
    assert item["status"] == "snoozed"
    assert item["snoozed_until"] == body["snoozed_until"]


def test_agenda_resume_is_idempotent_and_returns_item_to_pending(client, db):
    user, headers = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    payload = {"object_type": "health_protocol", "object_id": protocol.id}
    assert client.post(
        "/api/v1/agenda/snooze", headers=headers, json={**payload, "minutes": 30}
    ).status_code == 200

    first = client.post("/api/v1/agenda/resume", headers=headers, json=payload)
    second = client.post("/api/v1/agenda/resume", headers=headers, json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "pending"
    assert first.json()["idempotent"] is False
    assert second.json()["status"] == "pending"
    assert second.json()["idempotent"] is True
    event = db.query(HealthProtocolEvent).filter_by(
        user_id=user.id, protocol_id=protocol.id
    ).one()
    assert event.status == "pending"
    assert event.value is None


def test_agenda_snooze_retry_keeps_the_first_deadline(client, db):
    user, headers = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    payload = {
        "object_type": "health_protocol",
        "object_id": protocol.id,
        "minutes": 30,
    }

    first = client.post("/api/v1/agenda/snooze", headers=headers, json=payload)
    second = client.post("/api/v1/agenda/snooze", headers=headers, json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["snoozed_until"] == first.json()["snoozed_until"]


def test_agenda_snooze_can_be_set_again_after_the_deadline(client, db):
    user, headers = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    event = proto_svc.snooze_protocol(db, protocol.id, user.id, minutes=30)
    expired = datetime.now(UTC) - timedelta(minutes=1)
    event.value = {"minutes": 30, "snoozed_until": expired.isoformat()}
    db.commit()

    response = client.post(
        "/api/v1/agenda/snooze",
        headers=headers,
        json={"object_type": "health_protocol", "object_id": protocol.id, "minutes": 30},
    )

    assert response.status_code == 200, response.text
    renewed = datetime.fromisoformat(response.json()["snoozed_until"].replace("Z", "+00:00"))
    assert renewed > datetime.now(UTC)


def test_agenda_snooze_rejects_cross_user_and_unsupported_source(client, db):
    owner, _ = _user_and_headers(db)
    _, attacker_headers = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, owner.id)

    cross_user = client.post(
        "/api/v1/agenda/snooze",
        headers=attacker_headers,
        json={"object_type": "health_protocol", "object_id": protocol.id, "minutes": 30},
    )
    unsupported = client.post(
        "/api/v1/agenda/snooze",
        headers=attacker_headers,
        json={"object_type": "medication", "object_id": 1, "minutes": 30},
    )

    assert cross_user.status_code == 404
    assert unsupported.status_code == 400


def test_agenda_resume_does_not_reopen_completed_protocol(client, db):
    user, headers = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    proto_svc.complete_protocol(db, protocol.id, user.id)

    response = client.post(
        "/api/v1/agenda/resume",
        headers=headers,
        json={"object_type": "health_protocol", "object_id": protocol.id},
    )

    assert response.status_code == 400


def test_agenda_snooze_does_not_reopen_skipped_protocol(client, db):
    user, headers = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    proto_svc.skip_protocol(db, protocol.id, user.id, "no_time")

    response = client.post(
        "/api/v1/agenda/snooze",
        headers=headers,
        json={"object_type": "health_protocol", "object_id": protocol.id, "minutes": 30},
    )

    assert response.status_code == 400


def test_agenda_complete_uses_the_same_user_day_as_snooze(
    client, db, monkeypatch,
):
    from app.api import agenda as agenda_api
    from app.services import agenda_service

    user, headers = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    user_day = date(2026, 7, 21)
    monkeypatch.setattr(agenda_api, "get_user_today", lambda _db, _uid: user_day)
    monkeypatch.setattr(agenda_service, "get_user_today", lambda _db, _uid: user_day)

    response = client.post(
        "/api/v1/agenda/complete",
        headers=headers,
        json={"object_type": "health_protocol", "object_id": protocol.id},
    )

    assert response.status_code == 200, response.text
    event = db.query(HealthProtocolEvent).filter_by(
        user_id=user.id, protocol_id=protocol.id,
    ).one()
    assert event.event_date == user_day
    item = next(
        item for item in client.get("/api/v1/agenda/today", headers=headers).json()["items"]
        if item["source"] == {"object_type": "health_protocol", "object_id": protocol.id}
    )
    assert item["status"] == "completed"


def test_agenda_today_uses_one_date_snapshot(db, monkeypatch):
    from app.services import agenda_service

    user, _ = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    protocol.time_window = "morning"
    db.commit()
    calls = 0

    def moving_today(_db, _uid):
        nonlocal calls
        calls += 1
        return date(2026, 7, 20) if calls == 1 else date(2026, 7, 21)

    monkeypatch.setattr(agenda_service, "get_user_today", moving_today)

    result = agenda_service.today(db, user.id)

    assert result["agenda_date"] == "2026-07-20"
    assert calls == 1


def test_snooze_cannot_overwrite_a_concurrent_completion(db, monkeypatch):
    from app.utils.timezone import get_user_today

    user, _ = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    event = HealthProtocolEvent(
        user_id=user.id,
        protocol_id=protocol.id,
        event_date=get_user_today(db, user.id),
        status="pending",
        track="protocol",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    original_execute = db.execute
    interleaved = False

    def execute_with_completion(statement, *args, **kwargs):
        nonlocal interleaved
        if (
            not interleaved
            and getattr(getattr(statement, "table", None), "name", None)
            == HealthProtocolEvent.__tablename__
        ):
            interleaved = True
            original_execute(
                update(HealthProtocolEvent)
                .where(HealthProtocolEvent.id == event.id)
                .values(status="completed")
            )
            db.commit()
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", execute_with_completion)

    with pytest.raises(ValueError, match="已处理"):
        proto_svc.snooze_protocol(db, protocol.id, user.id, minutes=30)

    db.expire_all()
    assert db.query(HealthProtocolEvent).filter_by(id=event.id).one().status == "completed"


def test_resume_cannot_overwrite_a_concurrent_skip(db, monkeypatch):
    user, _ = _user_and_headers(db)
    protocol = proto_svc.create_water_cup_protocol(db, user.id)
    event = proto_svc.snooze_protocol(db, protocol.id, user.id, minutes=30)
    original_execute = db.execute
    interleaved = False

    def execute_with_skip(statement, *args, **kwargs):
        nonlocal interleaved
        if (
            not interleaved
            and getattr(getattr(statement, "table", None), "name", None)
            == HealthProtocolEvent.__tablename__
        ):
            interleaved = True
            original_execute(
                update(HealthProtocolEvent)
                .where(HealthProtocolEvent.id == event.id)
                .values(status="skipped", skip_reason="no_time")
            )
            db.commit()
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", execute_with_skip)

    with pytest.raises(ValueError, match="已处理"):
        proto_svc.resume_protocol(db, protocol.id, user.id)

    db.expire_all()
    assert db.query(HealthProtocolEvent).filter_by(id=event.id).one().status == "skipped"
