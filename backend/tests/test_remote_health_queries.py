"""Bounded health read contracts, using synthetic health records only."""
from datetime import UTC, date, datetime, timedelta
import json

import pytest
from sqlalchemy import event

from app.models.daily_health import DietRecord, ExerciseRecord, GarminData, WorkoutRecord
from app.models.sleep_record import SleepRecord
from app.models.user import User
from app.services.remote_health_queries import query_health


DAY = date(2025, 3, 9)


@pytest.fixture
def owners(db):
    users = [User(username=name, name=name, email=f"{name}@example.test", hashed_password="x")
             for name in ("remote_reader", "other_reader")]
    db.add_all(users)
    db.commit()
    return [user.id for user in users]


def _seed(db, user_id, day=DAY):
    db.add_all([
        GarminData(user_id=user_id, record_date=day, data_source="apple-watch",
                   total_sleep_duration=420, deep_sleep_duration=60),
        SleepRecord(user_id=user_id, record_date=day,
                    bedtime=datetime(2025, 3, 9, 5, tzinfo=UTC),
                    wake_time=datetime(2025, 3, 9, 12, tzinfo=UTC),
                    total_duration_minutes=420, sleep_quality=4, notes="PRIVATE"),
        DietRecord(user_id=user_id, record_date=day, meal_type="breakfast",
                   calories=123.456, protein=None, food_name="PRIVATE", notes="PRIVATE",
                   ai_raw_result="PRIVATE", source="fdc"),
        ExerciseRecord(user_id=user_id, record_date=day, exercise_type="running",
                       duration=30, notes="PRIVATE"),
        WorkoutRecord(user_id=user_id, workout_date=day, workout_type="running",
                      duration_seconds=1800, source="garmin", notes="PRIVATE",
                      route_data="PRIVATE", heart_rate_data="PRIVATE"),
    ])
    db.commit()


@pytest.mark.parametrize("kind,count", [("sleep", 2), ("diet", 1), ("exercise", 2)])
def test_only_authenticated_owner_and_allowlisted_fields(db, owners, kind, count):
    _seed(db, owners[0])
    _seed(db, owners[1], DAY + timedelta(days=1))
    result = query_health(db, owners[0], kind, DAY, DAY + timedelta(days=1), "America/New_York")
    assert len(result["records"]) == count
    assert result["coverage"]["missing_dates"] == ["2025-03-10"]
    assert result["coverage"]["total_records"] == count
    assert "PRIVATE" not in json.dumps(result)
    assert all("user_id" not in row for row in result["records"])
    assert all(row["record_date"] == "2025-03-09" for row in result["records"])
    assert all(row["source"] for row in result["records"])


def test_null_nutrition_is_not_zero_and_display_precision(db, owners):
    _seed(db, owners[0])
    result = query_health(db, owners[0], "diet", DAY, DAY, "UTC")
    assert result["records"][0]["protein_g"] is None
    assert result["records"][0]["calories_kcal"] == 123.46
    assert "absence is not zero" in result["coverage"]["meaning"]


def test_no_sleep_metrics_does_not_claim_sleep_coverage(db, owners):
    db.add(GarminData(user_id=owners[0], record_date=DAY, steps=1200))
    db.commit()
    result = query_health(db, owners[0], "sleep", DAY, DAY, "UTC")
    assert result["records"] == []
    assert result["coverage"]["missing_dates"] == [DAY.isoformat()]


def test_record_limit_and_missingness_are_independent(db, owners):
    db.add_all([DietRecord(user_id=owners[0], record_date=DAY, meal_type="snack")
                for _ in range(201)])
    db.add(DietRecord(user_id=owners[0], record_date=DAY + timedelta(days=1), meal_type="lunch"))
    db.commit()
    result = query_health(db, owners[0], "diet", DAY, DAY + timedelta(days=2), "UTC")
    assert len(result["records"]) == 200
    assert result["truncated"] is True
    assert result["coverage"]["total_records"] == 202
    assert result["coverage"]["missing_dates"] == ["2025-03-11"]
    assert result["coverage"]["incomplete_returned_dates"] == ["2025-03-09", "2025-03-10"]
    assert len(json.dumps(result)) < 200_000


@pytest.mark.parametrize("zone", ["America/New_York", "Pacific/Kiritimati", "Etc/GMT+12"])
def test_daily_labels_are_preserved_across_timezones_and_dst(db, owners, zone):
    _seed(db, owners[0])
    result = query_health(db, owners[0], "sleep", DAY, DAY, zone)
    assert result["timezone"] == zone
    assert {row["record_date"] for row in result["records"]} == {DAY.isoformat()}
    assert "not rebucketed" in result["date_semantics"]
    assert "wake" in result["date_semantics"]


def test_future_date_uses_requested_timezone(db, owners, monkeypatch):
    from app.services import remote_health_queries as queries

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2025, 3, 10, 0, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(queries, "datetime", FixedDatetime)
    query_health(db, owners[0], "sleep", date(2025, 3, 10), date(2025, 3, 10), "Pacific/Kiritimati")
    with pytest.raises(ValueError, match="future"):
        query_health(db, owners[0], "sleep", date(2025, 3, 10), date(2025, 3, 10), "America/New_York")


@pytest.mark.parametrize("kind,start,end,zone", [
    ("write", DAY, DAY, "UTC"),
    ("sleep", DAY, DAY, "../invalid"),
    ("sleep", DAY, DAY, ""),
    ("diet", DAY + timedelta(days=1), DAY, "UTC"),
    ("exercise", DAY, DAY + timedelta(days=31), "UTC"),
    ("diet", DAY, date(2999, 1, 1), "UTC"),
])
def test_invalid_queries_fail_before_database_access(kind, start, end, zone):
    with pytest.raises(ValueError):
        query_health(None, 1, kind, start, end, zone)


def test_exactly_31_days_allowed(db, owners):
    result = query_health(db, owners[0], "diet", DAY, DAY + timedelta(days=30), "UTC")
    assert len(result["coverage"]["missing_dates"]) == 31


def test_read_does_not_autoflush_pending_writes(db, owners):
    db.add(DietRecord(user_id=owners[0], record_date=DAY, meal_type="snack"))
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        result = query_health(db, owners[0], "diet", DAY, DAY, "UTC")
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert result["records"] == []
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements)


def test_arbitrary_source_and_type_text_are_not_exposed(db, owners):
    db.add(WorkoutRecord(user_id=owners[0], workout_date=DAY, workout_type="PRIVATE" * 10000,
                         source="PRIVATE" * 10000))
    db.commit()
    result = query_health(db, owners[0], "exercise", DAY, DAY, "UTC")
    assert result["records"][0]["exercise_type"] == "other"
    assert result["records"][0]["source"] == "unknown"
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("user_id", [None, 0, -1, True, "1"])
def test_invalid_principal_is_rejected_before_database_access(user_id):
    with pytest.raises(ValueError, match="user_id"):
        query_health(None, user_id, "diet", DAY, DAY, "UTC")


def test_combined_sources_share_one_result_limit(db, owners):
    db.add_all([ExerciseRecord(user_id=owners[0], record_date=DAY, exercise_type="walking")
                for _ in range(150)])
    db.add_all([WorkoutRecord(user_id=owners[0], workout_date=DAY, workout_type="running")
                for _ in range(150)])
    db.commit()
    result = query_health(db, owners[0], "exercise", DAY, DAY, "UTC")
    assert len(result["records"]) == 200
    assert result["coverage"]["total_records"] == 300
    assert result["truncated"] is True


def test_sleep_zero_is_observation_but_null_is_unknown(db, owners):
    db.add(GarminData(user_id=owners[0], record_date=DAY, total_sleep_duration=0))
    db.commit()
    result = query_health(db, owners[0], "sleep", DAY, DAY, "UTC")
    assert result["records"][0]["duration_minutes"] == 0
    assert result["records"][0]["deep_minutes"] is None
    assert result["coverage"]["missing_dates"] == []


def test_private_columns_are_never_selected(db, owners):
    _seed(db, owners[0])
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        for kind in ("sleep", "diet", "exercise"):
            query_health(db, owners[0], kind, DAY, DAY, "UTC")
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    forbidden = ("notes", "dream_description", "food_name", "food_items", "image_url",
                 "ai_raw_result", "ai_analysis", "route_data", "heart_rate_data")
    assert all(name not in statement for statement in statements for name in forbidden)
