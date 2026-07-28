"""Run Episode must use the same ACWR reliability boundary as HealthTwin."""

from datetime import datetime, timedelta, timezone

from app.models.daily_health import GarminData, WorkoutRecord
from app.models.user import User
from app.services.episode.run_episode_parser import _compute_acwr


def _user(db) -> User:
    user = User(name="run-episode-acwr-test")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _workout(db, user_id: int, *, now: datetime, days_ago: int, load: int) -> None:
    ended_at = now - timedelta(days=days_ago)
    db.add(
        WorkoutRecord(
            user_id=user_id,
            workout_date=ended_at.date(),
            start_time=ended_at - timedelta(minutes=30),
            end_time=ended_at,
            workout_type="running",
            duration_seconds=30 * 60,
            training_load=load,
            source="garmin",
            external_id=f"episode-acwr-{days_ago}",
        )
    )
    db.commit()


def _observed_days(db, user_id: int, *, now: datetime) -> None:
    for days_ago in range(28):
        db.add(
            GarminData(
                user_id=user_id,
                record_date=now.date() - timedelta(days=days_ago),
                data_source="garmin",
                steps=0,
            )
        )
    db.commit()


def test_first_run_without_chronic_baseline_has_no_acwr(db):
    now = datetime.now(timezone.utc)
    user = _user(db)
    _workout(db, user.id, now=now, days_ago=0, load=120)

    assert _compute_acwr(db, user.id, now) is None


def test_run_with_established_chronic_baseline_keeps_acwr(db):
    now = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)
    user = _user(db)
    _observed_days(db, user.id, now=now)
    _workout(db, user.id, now=now, days_ago=0, load=200)
    _workout(db, user.id, now=now, days_ago=8, load=70)
    _workout(db, user.id, now=now, days_ago=14, load=70)
    _workout(db, user.id, now=now, days_ago=21, load=70)

    assert _compute_acwr(db, user.id, now) == 1.95
