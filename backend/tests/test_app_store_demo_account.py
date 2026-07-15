"""PROOF that the App Store review demo account renders non-empty surfaces.

The #1 release risk: an App Store reviewer (or TestFlight first-run on a
simulator/review device) logs into the demo account WITHOUT HealthKit and must
see non-empty 今日(daily plan) / 时间线(timeline) / 每日工件(daily artifact).
This test drives the EXACT seeder core (scripts.seed_demo_account.seed_demo)
against the in-memory test DB and asserts all three are non-empty, so the
synthetic dataset is proven to produce populated review surfaces.
"""
# Importing ActionCard at module load registers the `action_cards` table on
# Base.metadata BEFORE the `db` fixture runs create_all. The agenda/daily-plan
# read chain queries action_cards; without this the in-memory schema lacks it.
from app.models.action_card import ActionCard  # noqa: F401
from app.models.user import User
from app.services.auth import AuthService

import pytest

from scripts.seed_demo_account import seed_demo


def test_demo_account_surfaces_are_non_empty(db):
    summary = seed_demo(
        db,
        email="reviewer@reva.health",
        password="Demo1234!",
        name="App审核演示",
        days=7,
    )

    # Onboarding loop ran (HealthProblem/Program/DailyOperatingPlan bootstrapped).
    assert summary["onboarding_completed"] is True

    # 今日 — daily plan must have actions.
    assert summary["daily_plan_actions"] > 0, "daily plan must not be empty for review"

    # 时间线 — timeline must have events.
    assert summary["timeline_events"] > 0, "timeline must not be empty for review"

    # 每日工件 — daily artifact must surface a top action.
    assert summary["daily_artifact_top_action"], "daily artifact must have a top_action"

    assert summary["verification"] == "PASS"
    assert summary["user_id"] > 0
    assert "password" not in summary


def test_demo_seed_is_idempotent(db):
    """Re-running against the same email reuses the user and re-verifies clean."""
    first = seed_demo(db, email="reviewer@reva.health", password="Demo1234!", name="演示", days=7)
    second = seed_demo(db, email="reviewer@reva.health", password="Demo1234!", name="演示", days=7)

    assert second["user_id"] == first["user_id"]
    assert second["daily_plan_actions"] > 0
    assert second["timeline_events"] > 0
    assert second["daily_artifact_top_action"]
    assert second["verification"] == "PASS"


def test_demo_seed_does_not_silently_rotate_an_existing_password(db):
    email = "review-password-policy@reva.health"
    original = "unique-original-review-password"
    seed_demo(db, email=email, password=original, name="演示", days=1)

    with pytest.raises(RuntimeError, match="password"):
        seed_demo(db, email=email, password="unexpected-new-password", name="演示", days=1)

    user = db.query(User).filter(User.email == email).one()
    assert AuthService.verify_password(original, user.hashed_password)
