"""P1a API 端到端测试：时序、training readiness、devices、body composition、hr-zones。"""
from datetime import date, datetime, time, timedelta
import pytest
from app.models.user import User
from app.models.daily_health import GarminData, HeartRateSample, SpO2Sample, SleepLevelInterval, WorkoutRecord
from app.models.garmin_timeseries import RespirationSample, HrvReading, StressSample
from app.models.workout_hr_zone import WorkoutHrZone
from app.models.garmin_device import GarminDevice
from app.models.weight import WeightRecord


@pytest.fixture
def test_user(db):
    u = User(
        username="tsuser",
        email="ts@example.com",
        hashed_password="x",
        name="TS",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def auth_headers(client, test_user):
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seed_nightly_data(db, test_user):
    """植入一些时序数据供 /nightly/me/{date} 查。"""
    d = date(2026, 4, 23)
    db.add_all([
        SpO2Sample(user_id=test_user.id, record_date=d, sample_time=time(2, 0), spo2_value=96, epoch_ms=1, source="garmin"),
        SpO2Sample(user_id=test_user.id, record_date=d, sample_time=time(3, 0), spo2_value=90, epoch_ms=2, source="garmin"),
        HeartRateSample(user_id=test_user.id, record_date=d, sample_time=time(2, 0), heart_rate=55),
        RespirationSample(user_id=test_user.id, record_date=d, sample_time=time(2, 0), respiration_rate=14.5, source="garmin"),
        HrvReading(user_id=test_user.id, record_date=d, reading_time=time(2, 5), hrv_value=48.0, reading_type="5min_avg"),
        StressSample(user_id=test_user.id, record_date=d, sample_time=time(2, 0), stress_value=15, source="garmin"),
        SleepLevelInterval(user_id=test_user.id, record_date=d, start_epoch_ms=1, end_epoch_ms=1000, activity_level="deep"),
    ])
    db.commit()
    return d


class TestNightlyTimeseriesAPI:
    def test_returns_all_metrics(self, client, auth_headers, seed_nightly_data):
        d = seed_nightly_data
        r = client.get(f"/api/v1/garmin/nightly/me/{d}", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["record_date"] == d.isoformat()
        assert body["counts"]["spo2"] == 2
        assert body["counts"]["hr"] == 1
        assert body["counts"]["respiration"] == 1
        assert body["counts"]["hrv"] == 1
        assert body["counts"]["stress"] == 1
        assert len(body["sleep_stages"]) == 1
        assert body["sleep_stages"][0]["level"] == "deep"

    def test_metric_filter(self, client, auth_headers, seed_nightly_data):
        d = seed_nightly_data
        r = client.get(f"/api/v1/garmin/nightly/me/{d}?metrics=spo2", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "spo2" in body["metrics"]
        assert "hr" not in body["metrics"]

    def test_empty_date_returns_empty_counts(self, client, auth_headers, test_user):
        r = client.get(f"/api/v1/garmin/nightly/me/2020-01-01", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for metric in ("spo2", "hr", "respiration", "hrv", "stress"):
            assert body["metrics"].get(metric) == []

    def test_unauth_is_401(self, client, seed_nightly_data):
        d = seed_nightly_data
        r = client.get(f"/api/v1/garmin/nightly/me/{d}")
        assert r.status_code == 401


class TestTrainingReadinessAPI:
    def test_returns_training_fields(self, client, auth_headers, db, test_user):
        d = date(2026, 4, 23)
        db.add(GarminData(
            user_id=test_user.id,
            record_date=d,
            training_readiness_score=75,
            training_readiness_level="high",
            training_status="productive",
            acute_load=320.0,
            load_ratio=1.1,
        ))
        db.commit()

        r = client.get(f"/api/v1/garmin/training/me/{d}", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["training_readiness_score"] == 75
        assert body["training_status"] == "productive"
        assert body["load_ratio"] == 1.1

    def test_missing_day_is_404(self, client, auth_headers, test_user):
        r = client.get("/api/v1/garmin/training/me/2020-01-01", headers=auth_headers)
        assert r.status_code == 404

    def test_trend(self, client, auth_headers, db, test_user):
        today = date.today()
        for i in range(5):
            db.add(GarminData(
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                training_readiness_score=70 + i,
            ))
        db.commit()

        r = client.get("/api/v1/garmin/training/me/trend?days=7", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 5
        assert all("training_readiness_score" in d for d in data)


class TestDevicesAPI:
    def test_returns_devices_with_hours_since_sync(self, client, auth_headers, db, test_user):
        now = datetime.now()
        db.add(GarminDevice(
            user_id=test_user.id,
            device_id="dev-1",
            display_name="Fenix 7X",
            model="Fenix 7X",
            last_sync_time=now - timedelta(hours=3),
            battery_level=80,
            is_primary=True,
        ))
        db.commit()

        r = client.get("/api/v1/garmin/devices/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "dev-1"
        assert data[0]["battery_level"] == 80
        assert data[0]["is_primary"] is True
        assert 2.5 < data[0]["hours_since_last_sync"] < 3.5

    def test_empty_list(self, client, auth_headers, test_user):
        r = client.get("/api/v1/garmin/devices/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []


class TestBodyCompositionAPI:
    def test_returns_history(self, client, auth_headers, db, test_user):
        db.add(WeightRecord(
            user_id=test_user.id,
            record_date=date.today(),
            weight=70.5,
            body_fat_percentage=18.0,
            muscle_mass_kg=35.0,
            source="garmin_index",
        ))
        db.commit()

        r = client.get("/api/v1/garmin/body-composition/me?days=7", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["weight"] == 70.5
        assert data[0]["body_fat_percentage"] == 18.0
        assert data[0]["source"] == "garmin_index"

    def test_source_filter(self, client, auth_headers, db, test_user):
        db.add_all([
            WeightRecord(user_id=test_user.id, record_date=date.today(), weight=70.0, source="manual"),
            WeightRecord(user_id=test_user.id, record_date=date.today() - timedelta(days=1), weight=70.5, source="garmin_index"),
        ])
        db.commit()

        r = client.get("/api/v1/garmin/body-composition/me?days=7&source=garmin_index", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["source"] == "garmin_index"


class TestWorkoutHrZonesAPI:
    def test_returns_zones_for_owner(self, client, auth_headers, db, test_user):
        w = WorkoutRecord(
            user_id=test_user.id,
            workout_date=date.today(),
            workout_type="running",
        )
        db.add(w)
        db.commit()
        db.refresh(w)

        db.add_all([
            WorkoutHrZone(workout_id=w.id, zone_index=1, zone_name="Zone 1", lower_bpm=100, upper_bpm=120, seconds_in_zone=600),
            WorkoutHrZone(workout_id=w.id, zone_index=2, zone_name="Zone 2", lower_bpm=120, upper_bpm=140, seconds_in_zone=1200),
        ])
        db.commit()

        r = client.get(f"/api/v1/garmin/workout/{w.id}/hr-zones", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["zone_index"] == 1
        assert data[1]["seconds_in_zone"] == 1200

    def test_not_owner_is_404(self, client, auth_headers, db):
        other = User(username="other", email="other@x.com", hashed_password="x", name="O", is_active=True, is_approved=True)
        db.add(other)
        db.commit()
        db.refresh(other)
        w = WorkoutRecord(user_id=other.id, workout_date=date.today(), workout_type="running")
        db.add(w)
        db.commit()
        db.refresh(w)

        r = client.get(f"/api/v1/garmin/workout/{w.id}/hr-zones", headers=auth_headers)
        assert r.status_code == 404
