from datetime import datetime, timedelta, timezone

from app.api.data_collection import get_credential_status
from app.models.user import GarminCredential, User


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
