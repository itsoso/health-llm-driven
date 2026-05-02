"""Garmin sync health probe — 覆盖 no_data / ok / stale / invalid_cred 4 case."""
from datetime import date, datetime, timedelta, timezone

from app.models.daily_health import GarminData
from app.models.user import GarminCredential, User
from app.services.garmin_sync_health import garmin_sync_health_snapshot


def _make_user(db, i: int) -> User:
    u = User(
        username=f"garminhealth_{i}",
        email=f"garminhealth_{i}@ex.com",
        hashed_password="x",
        name=f"用户{i}",
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_garmin_sync_health_empty_db_is_no_data(db):
    snap = garmin_sync_health_snapshot(db)
    assert snap["active_users"] == 0
    assert snap["status"] == "no_data"
    assert snap["last_sync_at"] is None
    assert snap["distinct_users_24h"] == 0
    assert snap["invalid_cred_users"] == 0
    assert snap["stale_users_7d"] == 0


def test_garmin_sync_health_recent_sync_and_data_is_ok(db):
    u = _make_user(db, 1)
    now = datetime.now(timezone.utc)

    db.add(GarminCredential(
        user_id=u.id,
        garmin_email="x@y.com",
        encrypted_password="enc",
        sync_enabled=True,
        credentials_valid=True,
        last_sync_at=now - timedelta(hours=2),
    ))
    db.add(GarminData(
        user_id=u.id,
        record_date=date.today(),
    ))
    db.commit()

    snap = garmin_sync_health_snapshot(db)
    assert snap["active_users"] == 1
    assert snap["distinct_users_24h"] == 1
    assert snap["status"] == "ok"
    assert snap["last_sync_age_hours"] is not None and snap["last_sync_age_hours"] <= 3
    assert snap["stale_users_7d"] == 0


def test_garmin_sync_health_stale_when_48h_old(db):
    u = _make_user(db, 2)
    now = datetime.now(timezone.utc)

    db.add(GarminCredential(
        user_id=u.id,
        garmin_email="x@y.com",
        encrypted_password="enc",
        sync_enabled=True,
        credentials_valid=True,
        last_sync_at=now - timedelta(hours=48),
    ))
    db.commit()

    snap = garmin_sync_health_snapshot(db)
    assert snap["active_users"] == 1
    assert snap["distinct_users_24h"] == 0
    assert snap["status"] == "stale"
    # 48h 前同步过, 但 7 天内零数据 → stale_users_7d = 1
    assert snap["stale_users_7d"] == 1


def test_garmin_sync_health_invalid_creds_counted(db):
    u = _make_user(db, 3)
    db.add(GarminCredential(
        user_id=u.id,
        garmin_email="x@y.com",
        encrypted_password="enc",
        sync_enabled=True,
        credentials_valid=False,  # ← expired creds
        last_sync_at=None,
    ))
    db.commit()

    snap = garmin_sync_health_snapshot(db)
    assert snap["invalid_cred_users"] == 1
    # creds invalid 不算 active
    assert snap["active_users"] == 0
    assert snap["status"] == "no_data"
