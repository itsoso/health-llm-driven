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


def test_garmin_credential_status_does_not_claim_future_sync_success(db):
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

    assert status["minutes_since_last_sync"] is None
    assert status["health"] == "stale"
    assert "时间" in status["last_error"]


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


def test_activity_partial_preserves_login_and_prior_success_until_full_success(db):
    from app.services.auth import garmin_credential_service
    user = _make_user(db)
    prior = datetime.now(timezone.utc) - timedelta(minutes=5)
    cred = GarminCredential(user_id=user.id, garmin_email='synthetic@example.invalid',
        encrypted_password='unused', credentials_valid=True, error_count=0,
        last_sync_at=prior, garth_session=encode_native_token_store('{"di_token":"synthetic","di_refresh_token":"synthetic"}'))
    db.add(cred);db.commit()
    for _ in range(4):
        assert garmin_credential_service.mark_activity_sync_partial(db,user.id)
    db.refresh(cred)
    assert cred.credentials_valid is True and cred.error_count == 0
    assert (cred.last_sync_at.replace(tzinfo=timezone.utc) if cred.last_sync_at.tzinfo is None else cred.last_sync_at.astimezone(timezone.utc)) == prior
    assert get_credential_status(current_user=user,db=db)['health']=='stale'
    assert _garmin_status(db,user.id,datetime.now(timezone.utc))['status']=='warning'
    assert not garmin_credential_service.mark_activity_sync_partial(db,user.id+1000)
    assert garmin_credential_service.update_sync_status(db,user.id)
    assert get_credential_status(current_user=user,db=db)["health"] == "stale"
    assert garmin_credential_service.update_sync_status(db,user.id,activities_verified=True)
    assert get_credential_status(current_user=user,db=db)['health']=='healthy'
    assert _garmin_status(db,user.id,datetime.now(timezone.utc))['status']=='ok'


def test_recent_success_does_not_hide_latest_sync_failure(db):
    from app.services.auth import garmin_credential_service
    user = _make_user(db)
    db.add(GarminCredential(user_id=user.id, garmin_email='synthetic@example.invalid',
        encrypted_password='unused', credentials_valid=True,
        last_sync_at=datetime.now(timezone.utc)))
    db.commit()
    garmin_credential_service.update_sync_error(db, user.id, 'temporary sync failure')
    status = get_credential_status(current_user=user, db=db)
    assert status['health'] == 'stale'
    assert status['last_error']
    assert status['credentials_valid'] is True
