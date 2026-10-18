"""Owned opt-in GPS session safety contracts; all coordinates are synthetic."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from app.schemas.daily_journey import (
    JourneyStart,
    JourneyStateChange,
    JourneyBatch,
    JourneyAnnotations,
)
from app.services import daily_journey as service
from app.models.daily_journey import DailyJourneySession, DailyJourneyPoint

NOW = datetime(2026, 10, 18, 3, tzinfo=timezone.utc)
CLIENT = str(uuid4())


def start_payload(**kw):
    return JourneyStart(
        **dict(
            request_id=str(uuid4()),
            client_id=CLIENT,
            timezone="Asia/Shanghai",
            retention_days=7,
            consent=True,
            **kw,
        )
    )


@pytest.fixture
def clock(monkeypatch):
    current = [NOW]
    monkeypatch.setattr(service, "utcnow", lambda: current[0])
    return current


@pytest.fixture
def owner(db):
    from app.models.user import User

    user = User(name="synthetic journey owner")
    other = User(name="synthetic other owner")
    db.add_all([user, other])
    db.commit()
    return user.id, other.id


def start(db, owner):
    return service.start_session(db, owner[0], start_payload())


def point(seconds=1, **kw):
    return dict(
        id=str(uuid4()),
        recorded_at=(NOW + timedelta(seconds=seconds)).isoformat(),
        latitude=31.2,
        longitude=121.4,
        accuracy_m=5,
        speed_mps=None,
        **kw,
    )


def upload(db, owner, session, points, client=CLIENT):
    return service.upload_points(
        db,
        owner[0],
        session["id"],
        JourneyBatch(client_id=client, segment=session["segment"], points=points),
    )


def state(db, owner, session, action, client=CLIENT):
    return service.change_state(
        db,
        owner[0],
        session["id"],
        JourneyStateChange(
            action=action, expected_version=session["version"], client_id=client
        ),
    )


def test_start_requires_explicit_consent_and_valid_timezone():
    for extra in (
        {"consent": 1},
        {"consent": False},
        {"timezone": "Mars/City"},
        {"retention_days": 2},
    ):
        payload = start_payload().model_dump()
        payload.update(extra)
        with pytest.raises(ValidationError):
            JourneyStart(**payload)


def test_start_idempotent_bound_to_owner_device_and_fixed_day(db, owner, clock):
    req = start_payload()
    first = service.start_session(db, owner[0], req)
    assert service.start_session(db, owner[0], req) == first
    assert first["deadline_at"] == datetime(2026, 10, 18, 16, tzinfo=timezone.utc)
    assert first["local_date"].isoformat() == "2026-10-18"
    with pytest.raises(HTTPException) as err:
        service.start_session(db, owner[0], start_payload())
    assert err.value.status_code == 409
    bad = req.model_copy(update={"client_id": str(uuid4())})
    with pytest.raises(HTTPException):
        service.start_session(db, owner[0], bad)
    assert service.start_session(db, owner[1], req)["id"] != first["id"]


def test_upload_immutable_duplicate_and_payload_encrypted(db, owner, clock):
    session = start(db, owner)
    sample = point()
    first = upload(db, owner, session, [sample, sample])
    assert first["accepted"] == 1 and first["duplicate"] == 1
    assert upload(db, owner, session, [sample])["duplicate"] == 1
    altered = {**sample, "latitude": 30.0}
    with pytest.raises(HTTPException) as err:
        upload(db, owner, session, [altered])
    assert err.value.status_code == 409
    raw = db.execute(text("SELECT payload FROM daily_journey_points")).scalar()
    assert "31.2" not in raw and "121.4" not in raw and raw.startswith("gAAAA")
    assert db.query(DailyJourneyPoint).count() == 1


def test_owner_and_device_isolation(db, owner, clock):
    session = start(db, owner)
    for fn in (service.get_session, service.review_session):
        with pytest.raises(HTTPException) as err:
            fn(db, owner[1], session["id"])
        assert err.value.status_code == 404
    with pytest.raises(HTTPException):
        upload(db, owner, session, [point()], client=str(uuid4()))
    assert service.list_sessions(db, owner[1], NOW.date()) == {"items": []}


def test_pause_resume_cas_and_old_segment_rejected(db, owner, clock):
    session = start(db, owner)
    clock[0] += timedelta(minutes=1)
    paused = state(db, owner, session, "pause")
    assert paused["status"] == "paused"
    assert state(db, owner, paused, "pause") == paused
    with pytest.raises(HTTPException):
        upload(db, owner, session, [point(61)])
    with pytest.raises(HTTPException):
        state(db, owner, session, "resume")
    with pytest.raises(HTTPException):
        state(db, owner, paused, "resume", client=str(uuid4()))
    clock[0] += timedelta(minutes=1)
    resumed = state(db, owner, paused, "resume")
    assert resumed["segment"] == 2
    with pytest.raises(HTTPException):
        upload(db, owner, session, [point()])
    with pytest.raises(HTTPException):
        upload(db, owner, resumed, [point()])
    ended = state(db, owner, resumed, "end", client=str(uuid4()))
    with pytest.raises(HTTPException):
        state(db, owner, ended, "resume")


@pytest.mark.parametrize(
    "patch",
    [
        {"latitude": float("nan")},
        {"longitude": float("inf")},
        {"latitude": 91},
        {"accuracy_m": -1},
        {"speed_mps": -1},
        {"latitude": True},
        {"recorded_at": "2026-10-18T03:00:00"},
    ],
)
def test_bad_sample_schema(patch):
    with pytest.raises(ValidationError):
        JourneyBatch(client_id=CLIENT, segment=1, points=[{**point(), **patch}])


def test_time_bounds_and_deadline(db, owner, clock):
    session = start(db, owner)
    for seconds in (-1, 121):
        with pytest.raises(HTTPException):
            upload(db, owner, session, [point(seconds)])
    clock[0] = session["deadline_at"]
    with pytest.raises(HTTPException):
        upload(db, owner, session, [{**point(), "recorded_at": session["deadline_at"]}])
    assert service.get_session(db, owner[0], session["id"])["status"] == "ended"
    assert service.start_session(db, owner[0], start_payload())["id"] != session["id"]


def test_delete_and_expiry_physically_remove_payload_but_never_resurrect(
    db, owner, clock
):
    req = start_payload()
    session = service.start_session(db, owner[0], req)
    upload(db, owner, session, [point()])
    service.delete_session(db, owner[1], session["id"])
    assert db.query(DailyJourneySession).count() == 1
    service.delete_session(db, owner[0], session["id"])
    service.delete_session(db, owner[0], session["id"])
    assert db.query(DailyJourneyPoint).count() == 0
    with pytest.raises(HTTPException) as err:
        service.start_session(db, owner[0], req)
    assert err.value.status_code == 410
    new_req = start_payload()
    new = service.start_session(db, owner[0], new_req)
    upload(db, owner, new, [point()])
    clock[0] = new["expires_at"]
    assert service.list_sessions(db, owner[0], NOW.date()) == {"items": []}
    assert service.purge_expired(db) == 1
    assert (
        db.query(DailyJourneySession).count()
        == db.query(DailyJourneyPoint).count()
        == 0
    )
    with pytest.raises(HTTPException):
        service.start_session(db, owner[0], new_req)


def test_review_splits_gaps_and_low_accuracy_no_tail_extrapolation(db, owner, clock):
    session = start(db, owner)
    clock[0] += timedelta(hours=2)
    samples = [
        point(0),
        point(150),
        point(300),
        {**point(400), "accuracy_m": 200},
        point(500),
        point(1000),
    ]
    upload(db, owner, session, samples)
    result = service.review_session(db, owner[0], session["id"])
    assert len(result["segments"]) == 3
    assert len(result["stops"]) == 1
    assert result["stops"][0]["duration_seconds"] == 300
    assert result["summary"]["observed_seconds"] == 300
    assert {"low_accuracy", "signal_gap"} <= {g["reason"] for g in result["gaps"]}
    assert all(s["mode"] == "unknown" for s in result["segments"])
    target = result["stops"][0]["id"]
    updated = service.annotate_session(
        db,
        owner[0],
        session["id"],
        JourneyAnnotations(
            expected_version=1,
            annotations=[{"target_id": target, "label": "自定义停留"}],
        ),
    )
    assert updated["version"] == 2
    assert (
        service.review_session(db, owner[0], session["id"])["stops"][0]["label"]
        == "自定义停留"
    )
    raw = db.execute(text("SELECT annotations FROM daily_journey_sessions")).scalar()
    assert "自定义停留" not in raw
    with pytest.raises(HTTPException):
        service.annotate_session(
            db,
            owner[0],
            session["id"],
            JourneyAnnotations(
                expected_version=2,
                annotations=[{"target_id": str(uuid4()), "label": "other"}],
            ),
        )


def test_batch_is_atomic_and_caps_are_enforced(db, owner, clock, monkeypatch):
    session = start(db, owner)
    with pytest.raises(HTTPException):
        upload(db, owner, session, [point(), point(-1)])
    assert db.query(DailyJourneyPoint).count() == 0
    monkeypatch.setattr(service, "MAX_POINTS", 1)
    with pytest.raises(HTTPException):
        upload(db, owner, session, [point(), point(2)])
    assert db.query(DailyJourneyPoint).count() == 0
    with pytest.raises(ValidationError):
        JourneyBatch(client_id=CLIENT, segment=1, points=[point() for _ in range(101)])


def test_gps_encryption_failure_and_ciphertext_corruption_fail_closed(
    db, owner, clock, monkeypatch, caplog
):
    from app.models import _encrypted
    from app.models._encrypted import StrictEncryptionError

    session = start(db, owner)
    original = _encrypted._fernet.encrypt

    def fail(_value):
        raise RuntimeError("private synthetic location 31.2,121.4")

    monkeypatch.setattr(_encrypted._fernet, "encrypt", fail)
    with pytest.raises(StrictEncryptionError) as error:
        upload(db, owner, session, [point()])
    assert "31.2" not in str(error.value) and "31.2" not in caplog.text
    assert error.value.__context__ is None
    db.rollback()
    assert db.query(DailyJourneyPoint).count() == 0
    monkeypatch.setattr(_encrypted._fernet, "encrypt", original)
    upload(db, owner, session, [point()])
    db.execute(
        text("UPDATE daily_journey_points SET payload='plaintext private location'")
    )
    db.commit()
    db.expire_all()
    with pytest.raises(StrictEncryptionError):
        service.review_session(db, owner[0], session["id"])
    assert "plaintext private location" not in caplog.text


def test_review_never_connects_pause_or_impossible_speed(db, owner, clock):
    session = start(db, owner)
    clock[0] += timedelta(seconds=100)
    upload(db, owner, session, [point(1), {**point(2), "latitude": 40.0}])
    paused = state(db, owner, session, "pause")
    clock[0] += timedelta(seconds=10)
    resumed = state(db, owner, paused, "resume")
    upload(db, owner, resumed, [point(110)])
    result = service.review_session(db, owner[0], session["id"])
    assert {"pause", "implausible_speed"} <= {gap["reason"] for gap in result["gaps"]}
    assert result["summary"]["distance_m"] == 0
    assert len(result["segments"]) == 3


def test_annotation_mode_is_explicit_user_correction(db, owner, clock):
    session = start(db, owner)
    upload(db, owner, session, [point()])
    target = service.review_session(db, owner[0], session["id"])["segments"][0]["id"]
    service.annotate_session(
        db,
        owner[0],
        session["id"],
        JourneyAnnotations(
            expected_version=1, annotations=[{"target_id": target, "mode": "cycling"}]
        ),
    )
    segment = service.review_session(db, owner[0], session["id"])["segments"][0]
    assert segment["mode"] == "cycling" and segment["mode_source"] == "user"


def test_api_auth_no_store_and_validation_does_not_echo_gps(db, owner, clock):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.daily_journey import router
    from app.api.deps import get_current_user_required
    from app.database import get_db
    from app.models.user import User

    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api)
    unauth = client.get("/daily-journeys/sessions?date=2026-10-18")
    assert unauth.status_code in (401, 403)
    assert unauth.headers["cache-control"] == "no-store"
    api.dependency_overrides[get_current_user_required] = lambda: db.get(User, owner[0])
    started = client.post(
        "/daily-journeys/sessions", json=start_payload().model_dump(mode="json")
    )
    assert started.status_code == 200
    sid = started.json()["id"]
    bad = client.post(
        f"/daily-journeys/sessions/{sid}/points",
        json={
            "client_id": CLIENT,
            "segment": 1,
            "points": [{**point(), "latitude": 191.23456789}],
        },
    )
    assert bad.status_code == 422
    assert "191.23456789" not in bad.text and "input" not in bad.text
    assert bad.headers["cache-control"] == "no-store"
    valid = client.post(
        f"/daily-journeys/sessions/{sid}/points",
        json={"client_id": CLIENT, "segment": 1, "points": [point()]},
    )
    assert valid.status_code == 200
    review = client.get(f"/daily-journeys/sessions/{sid}/review")
    assert review.status_code == 200 and review.headers["cache-control"] == "no-store"
    api.dependency_overrides[get_current_user_required] = lambda: db.get(User, owner[1])
    foreign = client.get(f"/daily-journeys/sessions/{sid}/review")
    assert foreign.status_code == 404 and "latitude" not in foreign.text
    assert client.delete(f"/daily-journeys/sessions/{sid}").status_code == 204
    assert db.query(DailyJourneyPoint).count() == 1


def test_exact_retention_start_and_empty_review_has_missing_window(db, owner, clock):
    session = start(db, owner)
    assert session["expires_at"] == NOW + timedelta(days=7)
    clock[0] += timedelta(minutes=10)
    review = service.review_session(db, owner[0], session["id"])
    assert review["summary"]["observed_seconds"] == 0
    assert review["gaps"] == [
        {"started_at": NOW, "ended_at": clock[0], "reason": "signal_gap"}
    ]


def test_mutations_produce_only_sanitized_durable_audit(db, owner, clock):
    from app.models.agent_audit_log import AgentAuditLog

    session = start(db, owner)
    state(db, owner, session, "pause")
    service.delete_session(db, owner[0], session["id"])
    audits = (
        db.query(AgentAuditLog)
        .filter_by(user_id=owner[0], agent_type="security_audit")
        .all()
    )
    assert {a.action for a in audits} == {
        "daily_journey_started",
        "daily_journey_paused",
        "daily_journey_deleted",
    }
    assert all(
        a.query is None and set(a.result_detail) <= {"session_id", "count", "status"}
        for a in audits
    )


def test_state_uncertain_retry_idempotent_but_not_after_other_changes(db, owner, clock):
    session = start(db, owner)
    paused = state(db, owner, session, "pause")
    assert state(db, owner, session, "pause") == paused
    assert state(db, owner, paused, "pause") == paused
    ended = state(db, owner, paused, "end")
    assert state(db, owner, paused, "end") == ended
    with pytest.raises(HTTPException):
        state(db, owner, session, "pause")


def test_late_delivery_after_end_or_midnight_preserves_capture_cutoff(db, owner, clock):
    session = start(db, owner)
    clock[0] += timedelta(seconds=60)
    ended = state(db, owner, session, "end")
    assert upload(db, owner, ended, [point(30)])["accepted"] == 1
    with pytest.raises(HTTPException):
        upload(db, owner, ended, [point(60)])
    second = service.start_session(db, owner[1], start_payload())
    clock[0] = second["deadline_at"] + timedelta(hours=1)
    result = service.upload_points(
        db,
        owner[1],
        second["id"],
        JourneyBatch(client_id=CLIENT, segment=1, points=[point(120)]),
    )
    assert result["accepted"] == 1 and result["session"]["status"] == "ended"
    with pytest.raises(HTTPException):
        service.upload_points(
            db,
            owner[1],
            second["id"],
            JourneyBatch(
                client_id=CLIENT,
                segment=1,
                points=[{**point(), "recorded_at": second["deadline_at"]}],
            ),
        )


def test_midnight_does_not_extend_prior_pause_window(db, owner, clock):
    session = start(db, owner)
    clock[0] += timedelta(seconds=60)
    paused = state(db, owner, session, "pause")
    clock[0] = paused["deadline_at"] + timedelta(hours=1)
    assert service.get_session(db, owner[0], session["id"])["status"] == "ended"
    assert upload(db, owner, paused, [point(30)])["accepted"] == 1
    with pytest.raises(HTTPException):
        upload(db, owner, paused, [point(61)])


def test_annotation_patch_preserves_unspecified_fields(db, owner, clock):
    session = start(db, owner)
    upload(db, owner, session, [point()])
    target = service.review_session(db, owner[0], session["id"])["segments"][0]["id"]
    service.annotate_session(
        db,
        owner[0],
        session["id"],
        JourneyAnnotations(
            expected_version=1, annotations=[{"target_id": target, "label": "我的通勤"}]
        ),
    )
    service.annotate_session(
        db,
        owner[0],
        session["id"],
        JourneyAnnotations(
            expected_version=2, annotations=[{"target_id": target, "mode": "walking"}]
        ),
    )
    segment = service.review_session(db, owner[0], session["id"])["segments"][0]
    assert segment["label"] == "我的通勤" and segment["mode"] == "walking"


def test_delete_and_expiry_purge_do_not_require_decryptable_annotations(
    db, owner, clock
):
    session = start(db, owner)
    upload(db, owner, session, [point()])
    db.execute(
        text("UPDATE daily_journey_sessions SET annotations='corrupt-ciphertext'")
    )
    db.commit()
    db.expire_all()
    service.delete_session(db, owner[0], session["id"])
    assert db.query(DailyJourneyPoint).count() == 0
    again = service.start_session(db, owner[0], start_payload())
    upload(db, owner, again, [point()])
    db.execute(
        text("UPDATE daily_journey_sessions SET annotations='corrupt-ciphertext'")
    )
    db.commit()
    db.expire_all()
    clock[0] = again["expires_at"]
    assert service.purge_expired(db) == 1
    assert (
        db.query(DailyJourneyPoint).count()
        == db.query(DailyJourneySession).count()
        == 0
    )


@pytest.mark.parametrize(
    "lat_step,seconds,expected",
    [
        (0.00045, 40, "walking"),
        (0.0054, 30, "vehicle"),
        (0.0, 40, "unknown"),
        (0.0015, 40, "unknown"),
    ],
)
def test_conservative_transport_estimates_with_visible_provenance(
    db, owner, clock, lat_step, seconds, expected
):
    session = start(db, owner)
    clock[0] += timedelta(minutes=10)
    samples = [
        {**point(index * seconds), "latitude": 31.2 + index * lat_step}
        for index in range(6)
    ]
    upload(db, owner, session, samples)
    segment = service.review_session(db, owner[0], session["id"])["segments"][0]
    assert segment["mode"] == expected
    assert segment["mode_source"] == "estimated"


def test_short_observations_across_gap_cannot_authorize_transport_estimate(
    db, owner, clock
):
    session = start(db, owner)
    clock[0] += timedelta(minutes=20)
    samples = [
        {**point(seconds), "latitude": 31.2 + index * 0.0054}
        for index, seconds in enumerate((0, 30, 600, 630))
    ]
    upload(db, owner, session, samples)
    review = service.review_session(db, owner[0], session["id"])
    assert len(review["segments"]) == 2
    assert all(segment["mode"] == "unknown" for segment in review["segments"])
    assert review["summary"]["observed_seconds"] == 60
