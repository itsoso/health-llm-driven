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
