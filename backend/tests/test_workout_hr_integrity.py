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
    }, 1)
    assert parsed["avg_cadence"] == 150
    assert parsed["max_cadence"] == 165

