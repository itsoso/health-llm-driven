"""Small, explicitly projected health reads for an authenticated remote caller.

Authorization belongs to the transport. Calendar labels have no source timezone
in these models: never reinterpret them as UTC or sum overlapping sources.
"""
from collections import Counter
from datetime import date, datetime, timedelta
import math
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.daily_health import DietRecord, ExerciseRecord, GarminData, WorkoutRecord
from app.models.sleep_record import SleepRecord
from app.utils.number_format import format_card_numbers

MAX_DAYS = 31
MAX_RECORDS = 200

_SOURCES = frozenset({
    "garmin", "apple-watch", "apple_health", "healthkit", "ringconn", "oura",
    "withings-app", "manual", "strava", "fdc", "china_food_composition", "unknown",
})
_EXERCISE_TYPES = frozenset({
    "running", "swimming", "cycling", "hiit", "cardio", "strength", "yoga",
    "walking", "hiking", "other", "pilates", "rowing", "elliptical",
    "跑步", "游泳", "骑行", "瑜伽", "步行", "力量训练", "俯卧撑", "平板支撑", "倒立",
})
_MEALS = frozenset({"breakfast", "lunch", "dinner", "snack", "早餐", "午餐", "晚餐", "加餐"})


def _projections(kind):
    if kind == "sleep":
        return [
            (GarminData, GarminData.record_date, "wearable_daily", {
                "source": GarminData.data_source,
                "duration_minutes": GarminData.total_sleep_duration,
                "deep_minutes": GarminData.deep_sleep_duration,
                "rem_minutes": GarminData.rem_sleep_duration,
                "light_minutes": GarminData.light_sleep_duration,
                "awake_minutes": GarminData.awake_duration,
                "sleep_score": GarminData.sleep_score,
            }),
            (SleepRecord, SleepRecord.record_date, "manual_sleep", {
                "duration_minutes": SleepRecord.total_duration_minutes,
                "quality_1_to_5": SleepRecord.sleep_quality,
                "wake_count": SleepRecord.wake_count,
            }),
        ]
    if kind == "diet":
        return [(DietRecord, DietRecord.record_date, "diet_record", {
            "source": DietRecord.source, "meal_type": DietRecord.meal_type,
            "calories_kcal": DietRecord.calories, "protein_g": DietRecord.protein,
            "carbs_g": DietRecord.carbs, "fat_g": DietRecord.fat, "fiber_g": DietRecord.fiber,
        })]
    return [
        (ExerciseRecord, ExerciseRecord.record_date, "manual_exercise", {
            "exercise_type": ExerciseRecord.exercise_type,
            "duration_minutes": ExerciseRecord.duration,
            "duration_seconds": ExerciseRecord.duration_seconds,
            "calories_kcal": ExerciseRecord.calories_burned,
            "distance_km": ExerciseRecord.distance,
            "reps": ExerciseRecord.reps, "sets": ExerciseRecord.sets,
        }),
        (WorkoutRecord, WorkoutRecord.workout_date, "workout", {
            "source": WorkoutRecord.source, "exercise_type": WorkoutRecord.workout_type,
            "duration_seconds": WorkoutRecord.duration_seconds,
            "distance_meters": WorkoutRecord.distance_meters,
            "calories_kcal": WorkoutRecord.calories,
        }),
    ]


def _safe_value(key, value):
    if key == "source":
        return value if value in _SOURCES else "unknown"
    if key == "exercise_type":
        return value if value in _EXERCISE_TYPES else "other"
    if key == "meal_type":
        return value if value in _MEALS else "unknown"
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None


def query_health(
    db: Session,
    user_id: int,
    kind: Literal["sleep", "diet", "exercise"],
    start_date: date,
    end_date: date,
    timezone: str,
) -> dict:
    """Read at most 31 stored calendar days and return at most 200 records.

    No flush/commit, relationships, free text, device identifiers, GPS, raw
    payloads or arbitrary query parameters are exposed. Counts describe stored
    records, not completeness of capture or a deduplicated health total.
    """
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("user_id must be a positive authenticated user ID")
    if kind not in ("sleep", "diet", "exercise"):
        raise ValueError("kind must be sleep, diet or exercise")
    if type(start_date) is not date or type(end_date) is not date:
        raise ValueError("start_date and end_date must be calendar dates")
    if not isinstance(timezone, str) or not timezone or len(timezone) > 64:
        raise ValueError("timezone must be an IANA timezone")
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("timezone must be an IANA timezone") from None
    if end_date < start_date or (end_date - start_date).days >= MAX_DAYS:
        raise ValueError("date range must contain 1 to 31 inclusive days")
    if end_date > datetime.now(zone).date():
        raise ValueError("future dates are not supported")

    records = []
    counts = Counter()
    returned_counts = Counter()
    with db.no_autoflush:
        for model, day_column, record_type, columns in _projections(kind):
            filters = [model.user_id == user_id, day_column >= start_date, day_column <= end_date]
            if model is GarminData:
                filters.append(or_(*(column.isnot(None) for key, column in columns.items() if key != "source")))
            daily_counts = db.query(day_column, func.count(model.id)).filter(*filters).group_by(day_column).all()
            for day, count in daily_counts:
                counts[day.isoformat()] += count
            rows = db.query(day_column, model.id, *columns.values()).filter(*filters).order_by(day_column, model.id).limit(MAX_RECORDS).all()
            for day, record_id, *values in rows:
                record = {key: _safe_value(key, value) for key, value in zip(columns, values)}
                record.update(record_date=day.isoformat(), record_type=record_type, record_id=record_id)
                if "source" not in record:
                    record["source"] = "manual"
                records.append(record)

    records.sort(key=lambda row: (row["record_date"], row["record_type"], row["record_id"]))
    records = records[:MAX_RECORDS]
    returned_counts.update(row["record_date"] for row in records)
    days = [(start_date + timedelta(days=offset)).isoformat()
            for offset in range((end_date - start_date).days + 1)]
    total = sum(counts.values())
    return format_card_numbers({
        "kind": kind,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": timezone,
        "date_semantics": (
            "Inclusive stored calendar date labels; sleep uses the recorded wake date. "
            "Source timezone is unavailable, so dates are not rebucketed. "
            "Requested timezone determines today's boundary only."
        ),
        "sources": sorted({row["source"] for row in records}),
        "sources_scope": "Sources represented in returned records only.",
        "records": records,
        "record_limit": MAX_RECORDS,
        "truncated": total > len(records),
        "coverage": {
            "meaning": (
                "Coverage counts stored records only; absence is not zero. Null metrics are unknown. "
                "Capture may be incomplete, including today. Different sources may overlap; "
                "records are not deduplicated and must not be blindly summed."
            ),
            "total_records": total,
            "returned_records": len(records),
            "missing_dates": [day for day in days if not counts[day]],
            "incomplete_returned_dates": [day for day in days if counts[day] > returned_counts[day]],
            "daily_record_counts": [{"date": day, "available": counts[day], "returned": returned_counts[day]} for day in days],
        },
    })
