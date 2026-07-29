"""Run Episode must use the same ACWR reliability boundary as HealthTwin."""

from datetime import date, datetime, timedelta, timezone

from app.models.daily_health import WorkoutRecord
from app.models.user import User
from app.services.episode.run_episode_parser import _compute_acwr, parse_run_episode


def _user(db) -> User:
    user = User(name="run-episode-acwr-test")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _workout(db, user_id: int, *, now: datetime, days_ago: int, load: int) -> None:
    ended_at = now - timedelta(days=days_ago)
    duration_minutes = 120 if days_ago == 0 else 30
    db.add(
        WorkoutRecord(
            user_id=user_id,
            workout_date=ended_at.date(),
            start_time=ended_at - timedelta(minutes=30),
            end_time=ended_at,
            workout_type="running",
            duration_seconds=duration_minutes * 60,
            training_load=load,
            source="garmin",
            external_id=f"episode-acwr-{days_ago}",
        )
    )
    db.commit()


def test_first_run_without_chronic_baseline_has_no_acwr(db):
    now = datetime.now(timezone.utc)
    user = _user(db)
    _workout(db, user.id, now=now, days_ago=0, load=120)

    assert _compute_acwr(db, user.id, now.date()) is None


def test_run_with_established_chronic_baseline_keeps_acwr(db):
    now = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)
    user = _user(db)
    _workout(db, user.id, now=now, days_ago=0, load=200)
    _workout(db, user.id, now=now, days_ago=8, load=70)
    _workout(db, user.id, now=now, days_ago=14, load=70)
    _workout(db, user.id, now=now, days_ago=21, load=70)

    assert _compute_acwr(db, user.id, now.date()) == 2.29


def test_episode_acwr_uses_persisted_local_workout_date(db, monkeypatch):
    user = _user(db)
    local_workout_date = date(2026, 7, 27)
    workout = WorkoutRecord(
        user_id=user.id,
        workout_date=local_workout_date,
        start_time=datetime(2026, 7, 27, 20, 30),
        end_time=datetime(2026, 7, 27, 21, 0),
        workout_type="running",
        duration_seconds=30 * 60,
        source="garmin",
        external_id="episode-local-date",
    )
    db.add(workout)
    db.commit()
    db.refresh(workout)
    captured: dict[str, date] = {}

    def fake_get_training_load(_self, _db, _user_id, *, as_of_date):
        captured["as_of_date"] = as_of_date
        return {"acwr": None}

    monkeypatch.setattr(
        "app.services.episode.run_episode_parser.ExerciseRecoveryService.get_training_load",
        fake_get_training_load,
    )

    parse_run_episode(db, user.id, workout)

    assert captured["as_of_date"] == local_workout_date
