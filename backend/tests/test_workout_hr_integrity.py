"""Synthetic Garmin ingestion regressions: missing samples stay missing."""

import json
from datetime import date

import pytest

from app.models.daily_health import WorkoutRecord
from app.models.user import User
from app.services import workout_sync


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "samples,native_zones,expected_points",
    [
        ({"unsupported": True}, [0, 0, 0, 0, 0], None),
        (None, [0, 0, 0, 0, 0], None),
        ({"heartRateSamples": [[0, 120], [10000, 130]]}, [0, 0, 0, 0, 0],
         [{"time": 0, "hr": 120}, {"time": 10, "hr": 130}]),
        ({"heartRateSamples": [[0, 120], [10000, 130]]}, [10, 20, 30, 40, 50],
         [{"time": 0, "hr": 120}, {"time": 10, "hr": 130}]),
    ],
)
async def test_sync_uses_samples_and_native_zones_only(
    db, monkeypatch, samples, native_zones, expected_points, existing
):
    user = User(name="synthetic-hr-integrity")
    db.add(user)
    db.commit()

    class Client:
        def get_activities_by_date(self, *_):
            return [{"activityId": 7654321}]

    service = object.__new__(workout_sync.WorkoutSyncService)
    service.client = Client()
    service.user_id = user.id
    monkeypatch.setattr(service, "_ensure_authenticated", lambda: None)
    parsed = {
        "user_id": user.id, "workout_date": date(2026, 1, 1),
        "workout_type": "running", "workout_name": "Synthetic activity",
        "duration_seconds": 60, "source": "garmin", "external_id": "7654321",
        "avg_heart_rate": 130, "max_heart_rate": 140,
        **{f"hr_zone_{i}_seconds": v for i, v in enumerate(native_zones, 1)},
    }
    monkeypatch.setattr(service, "_parse_activity", lambda *_: dict(parsed))
    historic_points = [{"time": 0, "hr": 110}]
    historic_zones = [1, 2, 3, 4, 5]
    if existing:
        historical = dict(parsed)
        historical["heart_rate_data"] = json.dumps(historic_points)
        historical.update({f"hr_zone_{i}_seconds": v for i, v in enumerate(historic_zones, 1)})
        db.add(WorkoutRecord(**historical))
        db.commit()

    async def details(_):
        return {"heart_rate_data": samples}

    monkeypatch.setattr(service, "get_activity_details", details)
    monkeypatch.setattr(workout_sync, "_invalidate_twin", lambda _: None)
    assert await service.sync_activities(db, user.id, days=1) == {"synced_count": 0 if existing else 1}
    record = db.query(WorkoutRecord).filter_by(user_id=user.id, external_id="7654321").one()
    points = json.loads(record.heart_rate_data) if record.heart_rate_data else None
    assert points == (historic_points if existing else expected_points)
    assert [getattr(record, f"hr_zone_{i}_seconds") for i in range(1, 6)] == (
        historic_zones if existing else native_zones
    )


def test_native_running_cadence_remains_steps_per_minute():
    service = object.__new__(workout_sync.WorkoutSyncService)
    service.user_id = 1
    parsed = service._parse_activity({
        "activityId": 7654321, "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-01-01T10:00:00", "duration": 60,
        "averageRunningCadenceInStepsPerMinute": 150,
        "maxRunningCadenceInStepsPerMinute": 165,
        "hrTimeInZones": [{"secsInZone": 1}, 2, {"secsInZone": 3}, 4, 5],
    }, 1)
    assert parsed["avg_cadence"] == 150
    assert parsed["max_cadence"] == 165
    assert [parsed[f"hr_zone_{i}_seconds"] for i in range(1, 6)] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
@pytest.mark.parametrize("samples", [None, {"unsupported": True}, {"heartRateSamples": [[0, 120], [10000, 130]]}])
@pytest.mark.parametrize("zones", [[0, 0, 0, 0, 0], [1, 2, 3, 4, 5]])
async def test_refresh_never_fabricates_curve_or_zones(db, monkeypatch, samples, zones):
    from app.api import workout as api
    from app.services.auth import GarminCredentialService

    user = User(name="synthetic-refresh")
    db.add(user)
    db.commit()
    historical_curve = json.dumps([{"time": 0, "hr": 110}])
    record = WorkoutRecord(
        user_id=user.id, workout_date=date(2026, 1, 1), workout_type="running",
        duration_seconds=60, avg_heart_rate=130, max_heart_rate=140,
        source="garmin", external_id="7654321", heart_rate_data=historical_curve,
        **{f"hr_zone_{i}_seconds": v for i, v in enumerate(zones, 1)},
    )
    db.add(record)
    db.commit()
    service = object.__new__(workout_sync.WorkoutSyncService)
    service.user_id = user.id

    async def details(_):
        return {"heart_rate_data": samples}

    monkeypatch.setattr(service, "get_activity_details", details)
    monkeypatch.setattr(workout_sync, "WorkoutSyncService", lambda **_: service)
    monkeypatch.setattr(GarminCredentialService, "get_decrypted_credentials", lambda *_: {
        "email": "synthetic@example.invalid", "password": "synthetic-test-only"
    })
    invalidated = []
    monkeypatch.setattr(api, "_invalidate_twin", invalidated.append)
    if samples is None and not any(zones):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as rejected:
            await api.refresh_workout_heart_rate(record.id, User(id=user.id + 10000), db)
        assert rejected.value.status_code == 404
        assert record.heart_rate_data == historical_curve
        assert invalidated == []
    result = await api.refresh_workout_heart_rate(record.id, user, db)
    if samples and samples.get("heartRateSamples"):
        assert result["status"] == "success"
        assert result["zones_calculated"] is False
        assert json.loads(record.heart_rate_data) == [{"time": 0, "hr": 120}, {"time": 10, "hr": 130}]
        assert invalidated == [user.id]
    else:
        assert result["status"] == "no_data"
        assert result["points_count"] == 0
        assert record.heart_rate_data == historical_curve
        assert invalidated == []
    assert [getattr(record, f"hr_zone_{i}_seconds") for i in range(1, 6)] == zones

