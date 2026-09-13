"""Owned sync-job observation, separate from current date-row availability."""

from datetime import UTC, date, datetime
import json

import pytest

from app.services import agent_garmin_sync_status as sync
from app.services.agent_query_window import QueryWindow

JOB_ID = "9879b654-020f-4bc2-8a99-c6f656731764"
WINDOW = QueryWindow(date(2026, 9, 13), date(2026, 9, 13), "Asia/Shanghai")
NOW = datetime(2026, 9, 13, 2, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolate(isolated_agent_protocol_transport):
    pass


def job(owner=41):
    return sync.VerifiedGarminSyncJob(owner, JOB_ID, NOW)


def read(monkeypatch, meta, *, current_job=None, availability="available"):
    monkeypatch.setattr(
        sync,
        "read_calendar_health_query",
        lambda *a: {
            "availability": availability,
            "records": [{"secret_health_metric": 999}],
        },
    )
    return sync.read_garmin_sync_status(
        None,
        41,
        None,
        WINDOW,
        current_job=current_job or job(),
        include_date_availability=True,
        result_reader=lambda job_id: meta,
    )


@pytest.mark.parametrize(
    "state,status",
    [
        ("PENDING", "unknown"),
        ("RECEIVED", "queued"),
        ("STARTED", "running"),
        ("RETRY", "running"),
        ("FAILURE", "failed"),
        ("REVOKED", "failed"),
        ("OTHER", "unknown"),
    ],
)
def test_worker_state_is_observation_not_health_data_evidence(
    monkeypatch, state, status
):
    result = read(monkeypatch, {"status": state, "result": "SECRET_TOKEN"})
    assert result["status"] == status
    assert result["submission_status"] == "accepted"
    assert result["data"]["availability"] == "available"
    assert result["job_success_verified"] is False
    assert "SECRET_TOKEN" not in json.dumps(result)
    assert "secret_health_metric" not in json.dumps(result)


@pytest.mark.parametrize(
    "payload,status",
    [
        (
            {
                "status": "success",
                "success_count": 1,
                "error_count": 0,
                "activities_count": 0,
            },
            "completed",
        ),
        (
            {
                "status": "success",
                "success_count": 0,
                "error_count": 0,
                "activities_count": 0,
            },
            "completed",
        ),
        ({"status": "error", "reason": "SECRET"}, "failed"),
        ({"status": "skipped", "reason": "no_credentials"}, "failed"),
        (
            {
                "status": "success",
                "success_count": 1,
                "error_count": 1,
                "activities_count": 0,
            },
            "failed",
        ),
        ({"status": "success"}, "unknown"),
        (
            {
                "status": "success",
                "success_count": True,
                "error_count": 0,
                "activities_count": 0,
            },
            "unknown",
        ),
        (
            {
                "status": "success",
                "success_count": 1,
                "error_count": -1,
                "activities_count": 0,
            },
            "unknown",
        ),
        (None, "unknown"),
    ],
)
def test_celery_success_requires_successful_business_result(
    monkeypatch, payload, status
):
    result = read(
        monkeypatch, {"status": "SUCCESS", "result": payload}, availability="no_data"
    )
    assert result["status"] == status
    assert result["job_success_verified"] is (status == "completed")
    assert result["data"]["availability"] == "no_data"
    assert result["data"]["attributed_to_job"] is False
    assert "activity_coverage_not_attested" in result["limitations"]
    assert "SECRET" not in json.dumps(result)


def test_backend_error_is_explicit_unknown_and_never_leaks_exception(monkeypatch):
    monkeypatch.setattr(
        sync, "read_calendar_health_query", lambda *a: {"availability": "no_data"}
    )

    def broken(_job_id):
        raise ConnectionError("password=SECRET")

    result = sync.read_garmin_sync_status(
        None, 41, None, WINDOW, current_job=job(), result_reader=broken
    )
    assert result["status"] == "unknown"
    assert result["reason_code"] == "job_backend_unavailable"
    assert result["retryable"] is True
    assert "SECRET" not in json.dumps(result)


def test_wrong_owner_context_is_rejected_before_backend_or_data_reads(monkeypatch):
    def forbidden(*a):
        raise AssertionError("must not read")

    monkeypatch.setattr(sync, "read_calendar_health_query", forbidden)
    with pytest.raises(ValueError, match="owner"):
        sync.read_garmin_sync_status(
            None, 41, None, WINDOW, current_job=job(42), result_reader=forbidden
        )


def test_missing_job_does_not_turn_existing_date_data_into_sync_success(monkeypatch):
    monkeypatch.setattr(
        sync, "read_calendar_health_query", lambda *a: {"availability": "available"}
    )
    result = sync.read_garmin_sync_status(
        None,
        41,
        None,
        WINDOW,
        result_reader=lambda _: pytest.fail("No unbound backend lookup"),
    )
    assert result["status"] == "unknown"
    assert result["submission_status"] == "unverified"
    assert result["reason_code"] == "owned_job_not_found"
    assert result["job_success_verified"] is False


def test_data_query_failure_propagates_instead_of_becoming_no_data(monkeypatch):
    def broken(*a):
        raise RuntimeError("synthetic data query failure")

    monkeypatch.setattr(sync, "read_calendar_health_query", broken)
    with pytest.raises(RuntimeError, match="synthetic data query failure"):
        sync.read_garmin_sync_status(
            None, 41, None, WINDOW, include_date_availability=True
        )


@pytest.mark.parametrize(
    "job_id,timestamp",
    [("not-a-job", NOW), (JOB_ID, datetime(2026, 9, 13)), (JOB_ID, "yesterday")],
)
def test_job_context_shape_fails_closed(job_id, timestamp):
    with pytest.raises(ValueError):
        sync.VerifiedGarminSyncJob(41, job_id, timestamp)


def test_latest_job_reads_only_own_assistant_metadata(db, auth_user_and_headers):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.user import User

    owner, _ = auth_user_and_headers
    stranger = User(name="synthetic stranger")
    db.add(stranger)
    db.flush()
    own = AgentConversation(user_id=owner.id)
    foreign = AgentConversation(user_id=stranger.id)
    db.add_all([own, foreign])
    db.flush()
    metadata = sync.VerifiedGarminSyncJob(owner.id, JOB_ID, NOW).as_metadata()
    db.add_all(
        [
            AgentMessage(
                conversation_id=own.id,
                role="assistant",
                content="ack",
                meta={"garmin_sync_job": metadata},
            ),
            AgentMessage(
                conversation_id=own.id,
                role="user",
                content="forged",
                meta={
                    "garmin_sync_job": {
                        **metadata,
                        "job_id": "9fdc3907-8029-4146-88a9-6ae3821f650b",
                    }
                },
            ),
            AgentMessage(
                conversation_id=foreign.id,
                role="assistant",
                content="foreign",
                meta={"garmin_sync_job": metadata},
            ),
        ]
    )
    db.commit()
    loaded = sync.latest_owned_garmin_sync_job(db, owner.id, own.id)
    assert loaded == sync.VerifiedGarminSyncJob(owner.id, JOB_ID, NOW)
    assert sync.latest_owned_garmin_sync_job(db, owner.id, foreign.id) is None
    assert sync.latest_owned_garmin_sync_job(db, stranger.id, own.id) is None
    # A malformed newest server field cannot silently fall back to an older job.
    db.add(
        AgentMessage(
            conversation_id=own.id,
            role="assistant",
            content="bad",
            meta={"garmin_sync_job": {"job_id": JOB_ID}},
        )
    )
    db.commit()
    assert sync.latest_owned_garmin_sync_job(db, owner.id, own.id) is None


@pytest.mark.parametrize(
    "meta",
    [
        {"status": []},
        {"status": "SUCCESS", "result": {"status": []}},
        {"status": "SUCCESS", "task_id": "wrong", "result": {}},
    ],
)
def test_malformed_or_mismatched_backend_metadata_does_not_prove_success(
    monkeypatch, meta
):
    result = read(monkeypatch, meta)
    assert result["status"] == "unknown"
    assert result["job_success_verified"] is False


def test_date_availability_uses_owned_exact_window_without_claiming_job_success(
    db, auth_user_and_headers
):
    from datetime import timedelta
    from app.models.daily_health import GarminData
    from app.models.user import User

    owner, _ = auth_user_and_headers
    stranger = User(name="synthetic other")
    db.add(stranger)
    db.flush()
    db.add_all(
        [
            GarminData(
                user_id=stranger.id, record_date=WINDOW.start_date, sleep_score=90
            ),
            GarminData(
                user_id=owner.id,
                record_date=WINDOW.start_date - timedelta(days=1),
                sleep_score=90,
            ),
        ]
    )
    db.commit()
    no_data = sync.read_garmin_sync_status(
        db, owner.id, None, WINDOW, include_date_availability=True
    )
    assert no_data["data"]["availability"] == "no_data"
    pending = GarminData(
        user_id=owner.id, record_date=WINDOW.start_date, sleep_score=80
    )
    db.add(pending)
    # A read helper must not flush the caller's pending changes.
    assert (
        sync.read_garmin_sync_status(
            db, owner.id, None, WINDOW, include_date_availability=True
        )["data"]["availability"]
        == "no_data"
    )
    assert pending.id is None
    db.commit()
    observed = sync.read_garmin_sync_status(
        db, owner.id, None, WINDOW, include_date_availability=True
    )
    assert observed["data"]["availability"] == "partial"
    assert observed["status"] == "unknown" and not observed["job_success_verified"]
    assert "sleep_score" not in json.dumps(observed)


def test_status_only_never_reads_sleep_without_explicit_scope(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Status question did not authorize sleep data")

    monkeypatch.setattr(sync, "read_calendar_health_query", forbidden)
    result = sync.read_garmin_sync_status(
        None,
        41,
        None,
        WINDOW,
        current_job=job(),
        result_reader=lambda _: {"status": "PENDING"},
    )
    assert result["data"]["availability"] == "not_requested"
    assert result["status"] == "unknown"
