"""Training-load reliability regressions.

ACWR is not interpretable without both recent load and a chronic baseline.
These tests pin the boundary so a single newly synced workout cannot become a
high-risk ``ACWR=4.00`` alert.
"""

from datetime import date, timedelta

from app.models.daily_health import GarminData, WorkoutRecord
from app.models.user import User
from app.services.exercise_recovery_service import ExerciseRecoveryService
from app.services.training_load_metrics import assess_acwr
from app.utils.timezone import get_user_today


def _user(db) -> User:
    user = User(name="training-load-test")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _workout(
    db,
    user_id: int,
    *,
    days_ago: int,
    load: int | None,
    duration_minutes: int = 30,
    source: str = "garmin",
) -> None:
    today = get_user_today(db, user_id)
    db.add(
        WorkoutRecord(
            user_id=user_id,
            workout_date=today - timedelta(days=days_ago),
            workout_type="running",
            duration_seconds=duration_minutes * 60,
            training_load=load,
            source=source,
            external_id=f"training-load-{days_ago}",
        )
    )
    db.commit()


def _unrelated_daily_health_rows(
    db,
    user_id: int,
    *,
    base_date: date,
    days: int = 28,
) -> None:
    """Daily vitals do not prove that workout sync covered a zero-load day."""
    for days_ago in range(days):
        db.add(
            GarminData(
                user_id=user_id,
                record_date=base_date - timedelta(days=days_ago),
                data_source="garmin",
                steps=0,
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
    assert result["acwr_unavailable_reason"] == "insufficient_data_coverage"


def test_established_baseline_keeps_real_overload_detection(db):
    user = _user(db)
    _workout(db, user.id, days_ago=0, load=200, duration_minutes=120)
    _workout(db, user.id, days_ago=8, load=70, duration_minutes=30)
    _workout(db, user.id, days_ago=14, load=70, duration_minutes=30)
    _workout(db, user.id, days_ago=21, load=70, duration_minutes=30)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr_reliable"] is True
    assert result["acwr"] == 2.29
    assert result["acwr_zone"] == "overtraining"
    assert result["acwr_unavailable_reason"] is None


def test_unrelated_daily_health_rows_do_not_fake_training_coverage(db):
    user = _user(db)
    _unrelated_daily_health_rows(
        db,
        user.id,
        base_date=get_user_today(db, user.id),
    )
    _workout(db, user.id, days_ago=0, load=200)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr"] is None
    assert result["acwr_reliable"] is False
    assert result["acwr_unavailable_reason"] == "insufficient_chronic_baseline"


def test_missing_baseline_week_fails_closed(db):
    user = _user(db)
    _workout(db, user.id, days_ago=0, load=200, duration_minutes=120)
    _workout(db, user.id, days_ago=8, load=70)
    _workout(db, user.id, days_ago=21, load=70)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr_reliable"] is False
    assert result["acwr"] is None
    assert result["baseline_weeks_with_load"] == 2
    assert result["acwr_unavailable_reason"] == "insufficient_chronic_baseline"


def test_daily_vitals_with_zero_training_baseline_do_not_create_acwr_4(db):
    user = _user(db)
    _unrelated_daily_health_rows(
        db,
        user.id,
        base_date=get_user_today(db, user.id),
    )
    _workout(db, user.id, days_ago=0, load=120)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr"] is None
    assert result["acwr_reliable"] is False
    assert result["acwr_unavailable_reason"] == "insufficient_chronic_baseline"


def test_tiny_baseline_load_does_not_create_high_risk_ratio(db):
    user = _user(db)
    _workout(db, user.id, days_ago=0, load=120, duration_minutes=120)
    for days_ago in (8, 14, 21):
        today = get_user_today(db, user.id)
        db.add(
            WorkoutRecord(
                user_id=user.id,
                workout_date=today - timedelta(days=days_ago),
                workout_type="running",
                duration_seconds=1,
                training_load=1,
                source="garmin",
                external_id=f"tiny-baseline-{days_ago}",
            )
        )
    db.commit()

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr"] is None
    assert result["acwr_reliable"] is False
    assert result["acwr_unavailable_reason"] == "insufficient_chronic_baseline"


def test_provider_training_load_values_do_not_mix_with_derived_trimp(db):
    """ACWR uses one derived TRIMP scale regardless of provider payloads."""
    user = _user(db)
    for days_ago, provider_load in ((0, 9999), (8, None), (14, 1), (21, 700)):
        _workout(
            db,
            user.id,
            days_ago=days_ago,
            load=provider_load,
            duration_minutes=30,
            source="garmin" if days_ago != 14 else "apple_health",
        )

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr_reliable"] is True
    assert result["acwr"] == 1.0
    assert result["load_method"] == "derived_trimp"


def test_negative_persisted_training_load_fails_closed(db):
    user = _user(db)
    _workout(db, user.id, days_ago=0, load=-1, duration_minutes=120)
    for days_ago in (8, 14, 21):
        _workout(db, user.id, days_ago=days_ago, load=70)

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["acwr"] is None
    assert result["acwr_reliable"] is False
    assert result["acwr_unavailable_reason"] == "invalid_training_load_data"


def test_non_finite_load_is_never_reliable():
    result = assess_acwr(
        [float("nan"), float("inf"), 10.0] + [20.0] * 25,
        observed_days_newest_first=[True] * 28,
    )

    assert result.acwr is None
    assert result.reliable is False
    assert result.unavailable_reason == "invalid_training_load_data"


def test_negative_load_is_never_reliable():
    result = assess_acwr(
        [-1.0, 120.0] + [20.0] * 26,
        observed_days_newest_first=[True] * 28,
    )

    assert result.acwr is None
    assert result.reliable is False
    assert result.unavailable_reason == "invalid_training_load_data"


def test_training_load_uses_user_local_today(db, monkeypatch):
    user = _user(db)
    local_today = date(2026, 7, 28)
    monkeypatch.setattr(
        "app.services.exercise_recovery_service.get_user_today",
        lambda _db, _user_id: local_today,
    )
    for days_ago, load, duration_minutes in (
        (0, 200, 120),
        (8, 70, 30),
        (14, 70, 30),
        (21, 70, 30),
    ):
        db.add(
            WorkoutRecord(
                user_id=user.id,
                workout_date=local_today - timedelta(days=days_ago),
                workout_type="running",
                duration_seconds=duration_minutes * 60,
                training_load=load,
                source="garmin",
                external_id=f"local-today-{days_ago}",
            )
        )
    db.commit()

    result = ExerciseRecoveryService().get_training_load(db, user.id)

    assert result["today_trimp"] == 180
    assert result["acwr_reliable"] is True


def test_recommendation_omits_unknown_acwr_from_reasoning(db):
    user = _user(db)
    _workout(db, user.id, days_ago=1, load=120)

    result = ExerciseRecoveryService().get_recommendation(db, user.id)

    assert result["acwr"] is None
    assert "ACWR None" not in result["reasoning"]
    assert any("慢性训练基线不足" in warning for warning in result["warnings"])
