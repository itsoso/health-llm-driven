"""PROOF that the App Store review demo account renders non-empty surfaces.

The #1 release risk: an App Store reviewer (or TestFlight first-run on a
simulator/review device) logs into the demo account WITHOUT HealthKit and must
see non-empty 今日(daily plan) / 时间线(timeline) / 每日工件(daily artifact).
This test drives the EXACT seeder core (scripts.seed_demo_account.seed_demo)
against the in-memory test DB and asserts all three are non-empty, so the
synthetic dataset is proven to produce populated review surfaces.
"""
from datetime import date

# Importing ActionCard at module load registers the `action_cards` table on
# Base.metadata BEFORE the `db` fixture runs create_all. The agenda/daily-plan
# read chain queries action_cards; without this the in-memory schema lacks it.
from app.models.action_card import ActionCard  # noqa: F401
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.daily_health import WorkoutAnalysisResult, WorkoutRecord
from app.models.daily_operating_plan import DailyOperatingPlan
from app.models.intervention_event import InterventionEvent
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.user import User
from app.models.workout_hr_zone import WorkoutHrZone
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
    assert summary["demo_conversation_id"] > 0
    assert summary["demo_conversation_messages"] == 2

    assert summary["verification"] == "PASS"
    assert summary["user_id"] > 0
    assert "password" not in summary


def test_demo_seed_is_idempotent(db):
    """Re-running against the same email reuses the user and re-verifies clean."""
    first = seed_demo(db, email="reviewer@reva.health", password="Demo1234!", name="演示", days=7)
    user = db.query(User).filter(User.id == first["user_id"]).one()
    unrelated = AgentConversation(
        user_id=user.id,
        title="审核员自建对话",
        session_key="agent-reviewer-owned",
    )
    db.add(unrelated)
    db.commit()

    second = seed_demo(db, email="reviewer@reva.health", password="Demo1234!", name="演示", days=7)

    assert second["user_id"] == first["user_id"]
    assert second["daily_plan_actions"] > 0
    assert second["timeline_events"] > 0
    assert second["daily_artifact_top_action"]
    assert second["verification"] == "PASS"
    demo_conversations = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.user_id == user.id,
            AgentConversation.session_key == "app-store-review-demo",
        )
        .all()
    )
    assert len(demo_conversations) == 1
    assert demo_conversations[0].id == second["demo_conversation_id"]
    assert second["demo_conversation_messages"] == 2
    assert (
        db.query(AgentConversation)
        .filter(AgentConversation.id == unrelated.id)
        .one()
        .title
        == "审核员自建对话"
    )


def test_demo_seed_removes_dependent_rows_before_parent_records(db):
    first = seed_demo(
        db,
        email="review-exam-reset@reva.health",
        password="Demo1234!",
        name="演示",
        days=1,
    )
    exam = MedicalExam(
        user_id=first["user_id"],
        exam_date=date.today(),
        exam_type="blood_routine",
    )
    db.add(exam)
    db.flush()
    db.add(
        MedicalExamItem(
            exam_id=exam.id,
            item_name="血红蛋白",
            value=140,
            unit="g/L",
        )
    )
    workout = (
        db.query(WorkoutRecord)
        .filter(WorkoutRecord.user_id == first["user_id"])
        .first()
    )
    db.add(
        WorkoutAnalysisResult(
            workout_id=workout.id,
            user_id=first["user_id"],
            source="review-reset-test",
        )
    )
    db.add(
        WorkoutHrZone(
            workout_id=workout.id,
            zone_index=2,
            seconds_in_zone=300,
        )
    )
    plan = (
        db.query(DailyOperatingPlan)
        .filter(DailyOperatingPlan.user_id == first["user_id"])
        .first()
    )
    db.add(
        InterventionEvent(
            user_id=first["user_id"],
            plan_id=plan.id,
            plan_date=plan.plan_date,
            action_key="review-reset-test",
            action_title="演示动作",
            feedback_status="completed",
            action_snapshot={},
        )
    )
    db.commit()
    db.expunge_all()

    second = seed_demo(
        db,
        email="review-exam-reset@reva.health",
        password="Demo1234!",
        name="演示",
        days=1,
    )

    assert second["verification"] == "PASS"
    assert db.query(MedicalExam).filter(MedicalExam.user_id == first["user_id"]).count() == 0
    assert db.query(MedicalExamItem).count() == 0
    assert db.query(WorkoutAnalysisResult).count() == 0
    assert db.query(WorkoutHrZone).count() == 0
    assert db.query(InterventionEvent).count() == 0


def test_demo_conversation_is_safe_and_review_ready(db):
    summary = seed_demo(
        db,
        email="review-conversation@reva.health",
        password="Demo1234!",
        name="演示",
        days=7,
    )

    conversation = (
        db.query(AgentConversation)
        .filter(AgentConversation.id == summary["demo_conversation_id"])
        .one()
    )
    messages = (
        db.query(AgentMessage)
        .filter(AgentMessage.conversation_id == conversation.id)
        .order_by(AgentMessage.id.asc())
        .all()
    )

    assert conversation.title.startswith("每日健康简报")
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "结合最近一周的数据，我今天最值得做什么？"
    assert "今天优先完成两件事" in messages[1].content
    assert "诊断" not in messages[1].content
    assert "治愈" not in messages[1].content


def test_secret_free_seed_summary_excludes_account_and_health_details(db):
    from scripts.seed_demo_account import _build_secret_free_summary

    summary = seed_demo(
        db,
        email="review-secret-free@reva.health",
        password="Demo1234!",
        name="演示",
        days=1,
    )

    public = _build_secret_free_summary(summary)

    assert set(public) == {
        "verification",
        "daily_plan_actions",
        "timeline_events",
        "demo_conversation_messages",
    }
    assert public["verification"] == "PASS"
    assert "review-secret-free@reva.health" not in str(public)


def test_demo_seed_does_not_silently_rotate_an_existing_password(db):
    email = "review-password-policy@reva.health"
    original = "unique-original-review-password"
    seed_demo(db, email=email, password=original, name="演示", days=1)

    with pytest.raises(RuntimeError, match="password"):
        seed_demo(db, email=email, password="unexpected-new-password", name="演示", days=1)

    user = db.query(User).filter(User.email == email).one()
    assert AuthService.verify_password(original, user.hashed_password)
