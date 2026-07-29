#!/usr/bin/env python3
"""Seed a fully-populated demo account for App Store review / TestFlight first-run.

WHY: the App Store reviewer (and any TestFlight first-run on a simulator/review
device) logs into a demo account WITHOUT HealthKit authorization. If 今日(daily
plan) / 时间线(timeline) / 每日工件(daily artifact) render empty, the build gets
rejected. This script injects normal-range synthetic records and PROVES via the
real read paths that all three surfaces are non-empty before printing the account.

It is HONEST (R4-safe): only realistic baseline records, NO fabricated
"improved outcomes" or efficacy claims.

The core is `seed_demo(db, ...)` so the proof test
(tests/test_app_store_demo_account.py) can drive the exact same path against the
in-memory test DB.

Usage (from backend/, venv active):
    APP_STORE_REVIEW_DEMO_PASSWORD='<unique secret>' \
        python scripts/seed_demo_account.py \
        --email reviewer@example.com --name 演示用户 --days 7

Re-runnable: if the email already exists, the user is reused and its synthetic
data is reset (idempotent).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

# Allow running as a script: add backend/ to sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.models.action_card import ActionCard  # noqa: F401 - register lazily-loaded table
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import GarminData, WaterIntake, WorkoutRecord
from app.models.medical_exam import MedicalExam
from app.models.sleep_record import SleepRecord
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.weight import WeightRecord
from app.services.auth import AuthService
from app.services.onboarding_bootstrap import ensure_initial_health_loop

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "demo_user_minimal.json"

DEFAULT_EMAIL = "demo@reva.health"
DEFAULT_NAME = "演示用户"
DEFAULT_DAYS = 7
DEMO_CONVERSATION_SESSION_KEY = "app-store-review-demo"


def _load_fixture() -> dict[str, Any]:
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _local_dt(d: date, hour: int) -> datetime:
    """A timezone-aware (UTC) datetime for a given date + local-ish hour.

    Timeline / artifact only care that the timestamp is tz-aware and within the
    lookback window; exact tz offset is not load-bearing for non-emptiness.
    """
    return datetime.combine(d, time(hour=hour), tzinfo=timezone.utc)


def _reset_synthetic_data(db: Session, user_id: int) -> None:
    """Idempotency: clear the rows this seeder injects so a re-run is clean.

    We only touch the synthetic tables seeded here (and the onboarding loop's
    plan/program/problem are upserted by ensure_initial_health_loop itself).
    """
    from app.models.daily_operating_plan import DailyOperatingPlan

    for model in (
        GarminData,
        WeightRecord,
        WaterIntake,
        BloodPressureRecord,
        SleepRecord,
        WorkoutRecord,
        MedicalExam,
        DailyOperatingPlan,
    ):
        db.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)
    db.commit()


def _get_or_create_user(
    db: Session,
    email: str,
    password: str,
    name: str,
    profile_cfg: dict,
    *,
    rotate_password: bool = False,
) -> User:
    user = db.query(User).filter(User.email == email).first()
    birth_date = date.fromisoformat(profile_cfg["birth_date"])
    gender_zh = profile_cfg.get("gender_zh", "男")

    if user is None:
        user = User(
            username=email.split("@")[0],
            email=email,
            hashed_password=AuthService.get_password_hash(password),
            name=name,
            birth_date=birth_date,
            gender=gender_zh,
            is_active=True,
            is_approved=True,
            onboarding_completed=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Re-seeding data must not silently rotate a production review account.
        # A credential change is deliberate and explicit via --rotate-password.
        password_matches = bool(
            user.hashed_password
            and AuthService.verify_password(password, user.hashed_password)
        )
        if not password_matches and not rotate_password:
            raise RuntimeError(
                "existing demo account password does not match; "
                "use --rotate-password for an intentional credential rotation"
            )
        if rotate_password:
            user.hashed_password = AuthService.get_password_hash(password)
        user.name = name
        user.birth_date = birth_date
        user.gender = gender_zh
        user.is_active = True
        user.is_approved = True
        db.commit()

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    profile.gender = profile_cfg.get("gender", "male")
    profile.birth_date = birth_date
    profile.height_cm = profile_cfg.get("height_cm")
    profile.current_weight_kg = profile_cfg.get("current_weight_kg")
    profile.primary_goal = profile_cfg.get("primary_goal", "general")
    db.commit()
    return user


def _inject_observations(db: Session, user_id: int, fixture: dict, days: int) -> int:
    """Insert normal-range synthetic observations over the last `days` days.

    Returns the number of rows inserted (for the printed/asserted summary).
    """
    today = date.today()
    tmpl = fixture["observation_template"]
    alt = fixture["observation_every_other_day"]
    garmin = tmpl["garmin_daily"]
    weight = tmpl["weight"]
    water = tmpl["water"]
    bp = alt["blood_pressure"]
    sleep = alt["sleep_record"]

    inserted = 0
    for offset in range(days):
        d = today - timedelta(days=offset)
        db.add(GarminData(user_id=user_id, record_date=d, **garmin))
        db.add(WeightRecord(user_id=user_id, record_date=d, **weight))
        db.add(
            WaterIntake(
                user_id=user_id,
                record_date=d,
                intake_time=_local_dt(d, 12),
                amount_ml=water["amount_ml"],
                drink_type=water["drink_type"],
            )
        )
        inserted += 3
        if offset % 2 == 0:
            db.add(
                BloodPressureRecord(
                    user_id=user_id,
                    record_date=d,
                    measured_at=_local_dt(d, 8),
                    systolic=bp["systolic"],
                    diastolic=bp["diastolic"],
                    pulse=bp["pulse"],
                )
            )
            db.add(
                SleepRecord(
                    user_id=user_id,
                    record_date=d,
                    bedtime=_local_dt(d - timedelta(days=1), sleep["bedtime_hour_local"]),
                    wake_time=_local_dt(d, sleep["wake_hour_local"]),
                    sleep_quality=sleep["sleep_quality"],
                    total_duration_minutes=sleep["total_duration_minutes"],
                )
            )
            inserted += 2
    db.commit()
    return inserted


def _inject_timeline_seed(db: Session, user_id: int, fixture: dict) -> int:
    """Seed the clean POSITIVE sources build_timeline actually reads.

    build_timeline reads only WorkoutRecord / AnomalyAlert / GarminData(sleep<65)
    / Medication / MedicalExam. For a healthy demo we seed only normal workouts
    (no alerts, no poor sleep, no medications, no exam). Workout events use a
    tz-AWARE occurred_at; mixing them with the tz-NAIVE occurred_at of exam/alert
    events would crash build_timeline's sort, so we keep the source homogeneous.
    """
    today = date.today()
    workouts = fixture["timeline_seed_events"]["workouts"]
    for workout in workouts:
        w_date = today - timedelta(days=workout["day_offset"])
        db.add(
            WorkoutRecord(
                user_id=user_id,
                workout_date=w_date,
                start_time=_local_dt(w_date, 7),
                end_time=_local_dt(w_date, 8),
                workout_type=workout["workout_type"],
                workout_name=workout["workout_name"],
                duration_seconds=workout["duration_seconds"],
                distance_meters=workout["distance_meters"],
                avg_heart_rate=workout["avg_heart_rate"],
                calories=workout.get("calories"),
            )
        )
    db.commit()
    return len(workouts)


def _inject_demo_conversation(
    db: Session,
    user_id: int,
    fixture: dict[str, Any],
) -> tuple[int, int]:
    """Rebuild only the deterministic App Store review conversation.

    The dedicated session key keeps the reset narrowly scoped. Conversations
    created by a reviewer remain untouched.
    """
    existing = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.user_id == user_id,
            AgentConversation.session_key == DEMO_CONVERSATION_SESSION_KEY,
        )
        .all()
    )
    for conversation in existing:
        db.delete(conversation)
    db.flush()

    cfg = fixture["agent_conversation"]
    now = datetime.now(timezone.utc)
    conversation = AgentConversation(
        user_id=user_id,
        title=f"{cfg['title_prefix']} · {now:%m-%d}",
        session_key=DEMO_CONVERSATION_SESSION_KEY,
        created_at=now - timedelta(minutes=1),
        updated_at=now,
    )
    db.add(conversation)
    db.flush()
    db.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content=cfg["user_message"],
                created_at=now - timedelta(minutes=1),
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=cfg["assistant_message"],
                created_at=now,
            ),
        ]
    )
    db.commit()
    return int(conversation.id), 2


def seed_demo(
    db: Session,
    *,
    email: str = DEFAULT_EMAIL,
    password: str | None = None,
    name: str = DEFAULT_NAME,
    days: int = DEFAULT_DAYS,
    fixture: dict[str, Any] | None = None,
    rotate_password: bool = False,
) -> dict[str, Any]:
    """Core seeder. Build a fully-populated demo user against `db` and VERIFY
    the three review surfaces are non-empty. Fails loud (raises) if any is empty.

    Returns the JSON-serializable summary dict.
    """
    days = max(1, min(int(days or DEFAULT_DAYS), 30))
    if not password:
        raise ValueError("a unique demo password is required")
    fixture = fixture or _load_fixture()

    user = _get_or_create_user(
        db,
        email,
        password,
        name,
        fixture["profile"],
        rotate_password=rotate_password,
    )
    _reset_synthetic_data(db, user.id)
    _inject_observations(db, user.id, fixture, days)
    _inject_timeline_seed(db, user.id, fixture)
    demo_conversation_id, demo_conversation_messages = _inject_demo_conversation(
        db,
        user.id,
        fixture,
    )

    # Trigger the real initial health loop (HealthProblem/Program/DailyOperatingPlan).
    user.onboarding_completed = True
    db.commit()
    bootstrap = ensure_initial_health_loop(db, user.id)

    # --- Verify non-empty via the REAL read paths (fail loud) ---
    from app.services.daily_operating_plan import build_daily_operating_plan
    from app.services.events_timeline_service import build_timeline
    from app.services.daily_artifact_service import build_daily_artifact

    plan = build_daily_operating_plan(db, user.id, plan_date=date.today())
    plan_actions = plan.get("actions") or []
    if len(plan_actions) == 0:
        raise RuntimeError("VERIFICATION FAILED: daily plan has 0 actions")

    timeline = build_timeline(db, user.id, days=30, limit=40)
    if len(timeline) == 0:
        raise RuntimeError("VERIFICATION FAILED: timeline has 0 events")

    artifact = build_daily_artifact(db, user.id)
    top_action = artifact.get("top_action")
    if not isinstance(top_action, dict) or not top_action.get("title"):
        raise RuntimeError(
            "VERIFICATION FAILED: daily artifact has no top_action "
            f"(empty_state={artifact.get('empty_state')})"
        )

    return {
        "user_id": user.id,
        "email": email,
        "onboarding_completed": bool(user.onboarding_completed),
        "daily_plan_actions": len(plan_actions),
        "timeline_events": len(timeline),
        "daily_artifact_top_action": top_action.get("title"),
        "demo_conversation_id": demo_conversation_id,
        "demo_conversation_messages": demo_conversation_messages,
        "bootstrap_problem": bootstrap["problem"]["name"],
        "bootstrap_program": bootstrap["program"]["name"],
        "verification": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed an App Store review demo account.")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=os.getenv("APP_STORE_REVIEW_DEMO_PASSWORD"))
    parser.add_argument(
        "--rotate-password",
        action="store_true",
        help="Intentionally replace an existing demo account password",
    )
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Days of synthetic observations (1-30)")
    args = parser.parse_args()
    if not args.password:
        parser.error(
            "provide --password or APP_STORE_REVIEW_DEMO_PASSWORD; "
            "there is no public default credential"
        )

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        summary = seed_demo(
            db,
            email=args.email,
            password=args.password,
            name=args.name,
            days=args.days,
            rotate_password=args.rotate_password,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
