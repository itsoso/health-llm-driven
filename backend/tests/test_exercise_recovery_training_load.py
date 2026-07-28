"""Training-load reliability regressions.

ACWR is not interpretable without both recent load and a chronic baseline.
These tests pin the boundary so a single newly synced workout cannot become a
high-risk ``ACWR=4.00`` alert.
"""

from datetime import date, timedelta

from app.models.daily_health import WorkoutRecord
from app.models.user import User
from app.services.exercise_recovery_service import ExerciseRecoveryService


def _user(db) -> User:
    user = User(name="training-load-test")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _workout(db, user_id: int, *, days_ago: int, load: int) -> None:
    db.add(
        WorkoutRecord(
            user_id=user_id,
            workout_date=date.today() - timedelta(days=days_ago),
            workout_type="running",
            duration_seconds=30 * 60,
            training_load=load,
            source="garmin",
            external_id=f"training-load-{days_ago}",
        )
    )
    db.commit()


def test_single_recent_workout_does_not_create_acwr_4_overload(db):
    user = _user(db)
    _workout(db, user.id, days_ago=1, load=120)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr"] is None
    assert result["acwr_zone"] == "unknown"
    assert result["acwr_reliable"] is False
    assert result["acwr_unavailable_reason"] == "insufficient_chronic_baseline"


def test_no_recent_training_does_not_publish_acwr(db):
    user = _user(db)
    _workout(db, user.id, days_ago=14, load=90)
    _workout(db, user.id, days_ago=21, load=90)
    _workout(db, user.id, days_ago=27, load=90)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acute_load_7d"] == 0
    assert result["acwr"] is None
    assert result["acwr_zone"] == "unknown"
    assert result["acwr_reliable"] is False
    assert result["acwr_unavailable_reason"] == "no_recent_training"


def test_established_baseline_keeps_real_overload_detection(db):
    user = _user(db)
    _workout(db, user.id, days_ago=0, load=200)
    _workout(db, user.id, days_ago=8, load=70)
    _workout(db, user.id, days_ago=14, load=70)
    _workout(db, user.id, days_ago=21, load=70)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr_reliable"] is True
    assert result["acwr"] == 1.95
    assert result["acwr_zone"] == "overtraining"
    assert result["acwr_unavailable_reason"] is None


def test_baseline_must_cover_each_prior_week(db):
    user = _user(db)
    _workout(db, user.id, days_ago=0, load=200)
    _workout(db, user.id, days_ago=21, load=70)
    _workout(db, user.id, days_ago=22, load=70)
    _workout(db, user.id, days_ago=23, load=70)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr"] is None
    assert result["acwr_reliable"] is False
    assert result["acwr_unavailable_reason"] == "insufficient_chronic_baseline"


def test_recommendation_omits_unknown_acwr_from_reasoning(db):
    user = _user(db)
    _workout(db, user.id, days_ago=1, load=120)

    result = ExerciseRecoveryService().get_recommendation(db, user.id)

    assert result["acwr"] is None
    assert "ACWR None" not in result["reasoning"]
    assert any("慢性训练基线不足" in warning for warning in result["warnings"])
