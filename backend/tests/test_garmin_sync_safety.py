from datetime import UTC, datetime, timedelta

import pytest

from app import scheduler
from app.models.user import GarminCredential, User
from app.scheduler import get_all_sync_enabled_users
from app.services.auth import garmin_credential_service
from app.services.data_collection.garmin_native_auth import encode_native_token_store
from app.services.garmin_session_manager import GarminSessionManager


def _credential(db, suffix: str) -> GarminCredential:
    user = User(
        username=f"garmin-safety-{suffix}",
        email=f"app-{suffix}@example.com",
        hashed_password="unused",
        name=f"Safety {suffix}",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return garmin_credential_service.save_credentials(
        db,
        user.id,
        f"garmin-{suffix}@example.com",
        "fake-password",
    )


def test_runtime_manager_never_caches_live_garmin_clients() -> None:
    manager = GarminSessionManager()

    assert not hasattr(manager, "_sessions")
    assert not hasattr(manager, "get_cached_session")
    assert not hasattr(manager, "cache_session")


def test_periodic_selection_accepts_native_token_with_stale_flags(db) -> None:
    credential = _credential(db, "stale-native")
    credential.garth_session = encode_native_token_store(
        '{"di_token":"periodic","di_refresh_token":"periodic-refresh"}'
    )
    credential.credentials_valid = False
    credential.requires_mfa = True
    db.commit()

    selected = get_all_sync_enabled_users(db)

    assert credential.user_id in {item["user_id"] for item in selected}


def test_periodic_selection_rejects_invalid_credentials_without_token(db) -> None:
    credential = _credential(db, "invalid-no-token")
    credential.credentials_valid = False
    db.commit()

    selected = get_all_sync_enabled_users(db)

    assert credential.user_id not in {item["user_id"] for item in selected}


@pytest.mark.asyncio
async def test_scheduler_workout_failure_is_not_reported_as_success(
    db,
    monkeypatch,
) -> None:
    credential = _credential(db, "workout-failure")
    old_last_sync = datetime.now(UTC) - timedelta(days=2)
    credential.last_sync_at = old_last_sync
    db.commit()
    success_calls = []

    class FakeGarminService:
        def __init__(self, *_args, **_kwargs) -> None:
            self.client = object()
            self._authenticated = True

        def sync_date_range(self, *_args, **_kwargs):
            return {"success_count": 1, "error_count": 0, "no_data_count": 0}

    class FailingWorkoutService:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def sync_activities(self, *_args, **_kwargs):
            raise RuntimeError("workout service unavailable")

    from app.services import sync_lock, workout_sync

    monkeypatch.setattr(scheduler, "GarminConnectService", FakeGarminService)
    monkeypatch.setattr(workout_sync, "WorkoutSyncService", FailingWorkoutService)
    monkeypatch.setattr(sync_lock, "acquire_sync_lock", lambda *_args: True)
    monkeypatch.setattr(sync_lock, "release_sync_lock", lambda *_args: None)
    monkeypatch.setattr(scheduler.session_manager, "can_sync", lambda *_args: (True, ""))
    monkeypatch.setattr(scheduler.session_manager, "record_error", lambda *_args: (False, 0))
    monkeypatch.setattr(
        scheduler.session_manager,
        "record_success",
        lambda *_args: success_calls.append(True),
    )

    result = await scheduler.sync_user_garmin_data(
        db,
        credential.user_id,
        credential.garmin_email,
        "fake-password",
        days=1,
    )

    db.refresh(credential)
    persisted_last_sync = credential.last_sync_at
    if persisted_last_sync and persisted_last_sync.tzinfo is None:
        persisted_last_sync = persisted_last_sync.replace(tzinfo=UTC)
    assert result["success"] is False
    assert persisted_last_sync == old_last_sync
    assert success_calls == []


@pytest.mark.asyncio
async def test_scheduler_dispatches_the_whole_sync_to_the_garmin_executor(
    monkeypatch,
) -> None:
    expected = {"success": True, "message": "isolated"}
    calls = []
    db_sentinel = object()

    async def fake_run(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return expected

    monkeypatch.setattr(scheduler, "run_garmin_blocking", fake_run)

    result = await scheduler.sync_user_garmin_data(
        db_sentinel,
        7,
        "garmin@example.com",
        "secret",
        days=2,
        is_cn=True,
    )

    assert result is expected
    assert calls == [
        (
            scheduler._sync_user_garmin_data_impl,
            (db_sentinel, 7, "garmin@example.com", "secret"),
            {"days": 2, "is_cn": True, "retry_count": 0},
        )
    ]
