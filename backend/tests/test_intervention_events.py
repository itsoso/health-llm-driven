"""InterventionEvent append-only event stream tests."""

from datetime import date

from app.models.intervention_event import InterventionEvent
from tests.conftest import create_authenticated_user


def test_intervention_event_persists_supported_event_types(db):
    user, _ = create_authenticated_user(db)
    event_types = ["suggested", "accepted", "adjusted", "completed", "skipped", "verified"]

    for event_type in event_types:
        db.add(
            InterventionEvent(
                user_id=user.id,
                plan_date=date.today(),
                action_key=f"action.{event_type}",
                action_title=f"Action {event_type}",
                feedback_status=event_type,
                action_snapshot={"event_type": event_type},
            )
        )
    db.commit()

    rows = (
        db.query(InterventionEvent)
        .filter(InterventionEvent.user_id == user.id)
        .order_by(InterventionEvent.id)
        .all()
    )
    assert [row.feedback_status for row in rows] == event_types


def test_intervention_event_queries_are_scoped_by_user(db):
    user_a, _ = create_authenticated_user(db)
    user_b, _ = create_authenticated_user(db)
    db.add_all(
        [
            InterventionEvent(
                user_id=user_a.id,
                plan_date=date.today(),
                action_key="shared.action",
                action_title="A action",
                feedback_status="completed",
                action_snapshot={},
            ),
            InterventionEvent(
                user_id=user_b.id,
                plan_date=date.today(),
                action_key="shared.action",
                action_title="B action",
                feedback_status="skipped",
                action_snapshot={},
            ),
        ]
    )
    db.commit()

    rows = db.query(InterventionEvent).filter(InterventionEvent.user_id == user_a.id).all()
    assert len(rows) == 1
    assert rows[0].action_title == "A action"
