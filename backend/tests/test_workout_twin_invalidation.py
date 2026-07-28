"""Workout mutations must invalidate Twin and derived Safety state."""

from datetime import date

import pytest
from starlette.requests import Request

from app.api import workout as workout_api
from app.models.daily_health import WorkoutRecord
from app.models.user import User
from app.schemas.workout import (
    Feeling,
    WorkoutRecordCreate,
    WorkoutRecordUpdate,
    WorkoutType,
)


def _user(db) -> User:
    user = User(name="workout-invalidation-test")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_update_delete_workout_invalidate_twin(db, monkeypatch):
    user = _user(db)
    invalidated: list[int] = []
    monkeypatch.setattr(workout_api, "_invalidate_twin", invalidated.append)

    created = workout_api.create_workout(
        WorkoutRecordCreate(
            workout_date=date(2026, 7, 27),
            workout_type=WorkoutType.WALKING,
            duration_seconds=600,
        ),
        user,
        db,
    )
    workout_api.update_workout(
        created.id,
        WorkoutRecordUpdate(feeling=Feeling.GOOD),
        user,
        db,
    )
    workout_api.delete_workout(created.id, user, db)

    assert invalidated == [user.id, user.id, user.id]
    assert db.query(WorkoutRecord).filter(WorkoutRecord.id == created.id).first() is None


def test_negative_training_load_is_rejected_at_api_boundary():
    try:
        WorkoutRecordCreate(
            workout_date=date(2026, 7, 27),
            workout_type=WorkoutType.RUNNING,
            duration_seconds=600,
            training_load=-1,
        )
    except ValueError:
        return

    raise AssertionError("negative training_load must fail validation")


@pytest.mark.asyncio
async def test_successful_garmin_sync_invalidates_twin(db, monkeypatch):
    """A device resync must not leave the previous ACWR/Safety result cached."""
    from app.services import auth, sync_lock, workout_sync
    from app.services.data_collection import garmin_connect

    user = _user(db)
    invalidated: list[int] = []
    released: list[int] = []

    class FakeCredentialService:
        def get_decrypted_credentials(self, _db, user_id):
            assert user_id == user.id
            return {
                "email": "garmin@example.com",
                "password": "secret",
                "is_cn": False,
            }

    class FakeGarminConnectService:
        def __init__(self, **_kwargs):
            self.client = object()
            self._authenticated = True

        def _ensure_authenticated(self, _db):
            return None

    class FakeWorkoutSyncService:
        def __init__(self, **_kwargs):
            pass

        async def sync_activities(self, _db, user_id, days):
            assert user_id == user.id
            assert days == 7
            return {"synced_count": 2}

    monkeypatch.setattr(auth, "GarminCredentialService", FakeCredentialService)
    monkeypatch.setattr(
        garmin_connect,
        "GarminConnectService",
        FakeGarminConnectService,
    )
    monkeypatch.setattr(workout_sync, "WorkoutSyncService", FakeWorkoutSyncService)
    monkeypatch.setattr(sync_lock, "acquire_sync_lock", lambda _db, _uid: True)
    monkeypatch.setattr(
        sync_lock,
        "release_sync_lock",
        lambda _db, uid: released.append(uid),
    )
    monkeypatch.setattr(workout_api, "_invalidate_twin", invalidated.append)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/workout/me/sync-garmin",
            "headers": [],
            "query_string": b"",
            "client": ("test", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    endpoint = getattr(
        workout_api.sync_garmin_activities,
        "__wrapped__",
        workout_api.sync_garmin_activities,
    )
    result = await endpoint(
        request=request,
        days=7,
        current_user=user,
        db=db,
    )

    assert result["synced_count"] == 2
    assert invalidated == [user.id]
    assert released == [user.id]


@pytest.mark.asyncio
async def test_central_workout_sync_invalidates_twin_after_persisting_activity(
    db,
    monkeypatch,
):
    """Every caller of the central Garmin writer must inherit cache invalidation."""
    from app.services import workout_sync

    user = _user(db)
    invalidated: list[int] = []

    class FakeClient:
        @staticmethod
        def get_activities_by_date(_start_date, _end_date):
            return [{"activityId": "central-sync-activity"}]

    service = object.__new__(workout_sync.WorkoutSyncService)
    service.client = FakeClient()
    service.user_id = user.id
    monkeypatch.setattr(service, "_ensure_authenticated", lambda: None)
    monkeypatch.setattr(
        service,
        "_parse_activity",
        lambda _activity, user_id: {
            "user_id": user_id,
            "workout_date": date(2026, 7, 27),
            "workout_type": "walking",
            "workout_name": "Central sync test",
            "duration_seconds": 600,
            "source": "garmin",
            "external_id": "central-sync-activity",
        },
    )

    async def no_details(_activity_id):
        return {}

    monkeypatch.setattr(service, "get_activity_details", no_details)
    monkeypatch.setattr(
        workout_sync,
        "_invalidate_twin",
        invalidated.append,
        raising=False,
    )

    result = await service.sync_activities(db, user.id, days=7)

    assert result == {"synced_count": 1}
    assert invalidated == [user.id]
    assert (
        db.query(WorkoutRecord)
        .filter(
            WorkoutRecord.user_id == user.id,
            WorkoutRecord.external_id == "central-sync-activity",
        )
        .one()
    )


@pytest.mark.asyncio
async def test_central_workout_sync_does_not_invalidate_without_changes(
    db,
    monkeypatch,
):
    from app.services import workout_sync

    user = _user(db)
    invalidated: list[int] = []

    class FakeClient:
        @staticmethod
        def get_activities_by_date(_start_date, _end_date):
            return []

    service = object.__new__(workout_sync.WorkoutSyncService)
    service.client = FakeClient()
    service.user_id = user.id
    monkeypatch.setattr(service, "_ensure_authenticated", lambda: None)
    monkeypatch.setattr(
        workout_sync,
        "_invalidate_twin",
        invalidated.append,
        raising=False,
    )

    result = await service.sync_activities(db, user.id, days=7)

    assert result == {"synced_count": 0}
    assert invalidated == []
