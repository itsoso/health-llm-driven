from datetime import datetime, timedelta, timezone

from app.api.data_collection import get_credential_status
from app.api.data_health import _garmin_status
from app.models.user import GarminCredential, User
from app.services.data_collection.garmin_native_auth import encode_native_token_store


def _make_user(db) -> User:
    user = User(
        username="garmin_status_user",
        email="garmin_status@example.com",
        hashed_password="x",
        name="Garmin Status",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_garmin_credential_status_clamps_future_sync_age(db):
    user = _make_user(db)
    db.add(GarminCredential(
        user_id=user.id,
        garmin_email="x@example.com",
        encrypted_password="enc",
        sync_enabled=True,
        credentials_valid=True,
        last_sync_at=datetime.now(timezone.utc) + timedelta(hours=8),
    ))
    db.commit()

    status = get_credential_status(current_user=user, db=db)

    assert status["minutes_since_last_sync"] == 0
    assert status["health"] == "healthy"


def test_garmin_credential_status_surfaces_mfa_as_actionable_error(db):
    user = _make_user(db)
    db.add(GarminCredential(
        user_id=user.id,
        garmin_email="x@example.com",
        encrypted_password="enc",
        sync_enabled=True,
        credentials_valid=True,
        requires_mfa=True,
        last_sync_at=None,
    ))
    db.commit()

    status = get_credential_status(current_user=user, db=db)

    assert status["bound"] is True
    assert status["health"] == "error"
    assert status["requires_mfa"] is True
    assert "验证" in status["last_error"]


def test_data_health_accepts_native_token_without_synthetic_expiry(db):
    user = _make_user(db)
    db.add(GarminCredential(
        user_id=user.id,
        garmin_email="x@example.com",
        encrypted_password="enc",
        sync_enabled=True,
        credentials_valid=True,
        garth_session=encode_native_token_store(
            '{"di_token":"status-token","di_refresh_token":"status-refresh"}'
        ),
        session_expires_at=None,
        last_sync_at=datetime.now(timezone.utc),
    ))
    db.commit()

    status = _garmin_status(db, user.id, datetime.now(timezone.utc))

    assert status["session_valid"] is True
    assert status["status"] == "ok"
