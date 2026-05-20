"""Daily Plan action feedback protocol tests."""

from datetime import date

from tests.conftest import create_authenticated_user


def test_daily_plan_action_feedback_creates_intervention_event(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    plan_resp = client.get("/api/v1/daily-plan/me", headers=headers)
    assert plan_resp.status_code == 200
    action = plan_resp.json()["actions"][0]
    action_key = action["action_key"]

    resp = client.post(
        f"/api/v1/daily-plan/me/actions/{action_key}/feedback",
        headers=headers,
        json={"status": "done", "reason": "晨起已测量"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action_key"] == action_key
    assert body["status"] == "done"
    assert body["reason"] == "晨起已测量"

    from app.models.intervention_event import InterventionEvent

    rows = db.query(InterventionEvent).filter(InterventionEvent.user_id == user.id).all()
    assert len(rows) == 1
    assert rows[0].plan_date == date.today()
    assert rows[0].action_key == action_key
    assert rows[0].action_title == action["title"]
    assert rows[0].feedback_status == "done"


def test_daily_plan_action_feedback_rejects_unknown_action(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/daily-plan/me/actions/unknown.action/feedback",
        headers=headers,
        json={"status": "done"},
    )

    assert resp.status_code == 404


def test_daily_plan_action_event_endpoint_records_completed_event(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    plan_resp = client.get("/api/v1/daily-plan/me", headers=headers)
    assert plan_resp.status_code == 200
    action = plan_resp.json()["actions"][0]
    action_key = action["action_key"]

    resp = client.post(
        f"/api/v1/daily-plan/actions/{action_key}/events",
        headers=headers,
        json={"event_type": "completed", "payload": {"source": "test"}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["action_id"] == action_key
    assert body["event_type"] == "completed"
    assert body["action_state"] == "completed"

    from app.models.intervention_event import InterventionEvent

    rows = db.query(InterventionEvent).filter(InterventionEvent.user_id == user.id).all()
    assert len(rows) == 1
    assert rows[0].feedback_status == "completed"
    assert rows[0].action_snapshot["event_payload"] == {"source": "test"}


def test_daily_plan_action_event_endpoint_rejects_unknown_event_type(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/daily-plan/actions/measurement.weight_waist/events",
        headers=headers,
        json={"event_type": "done"},
    )

    assert resp.status_code == 422


def test_daily_plan_action_event_endpoint_prevents_cross_user_action_write(client, db, auth_user_and_headers):
    owner, _ = auth_user_and_headers

    from app.models.action_card import ActionCard

    card = ActionCard(
        user_id=owner.id,
        title="只属于用户 A 的行动",
        content="content",
        status="active",
        user_decision="accepted",
        metric_key="sleep_duration_hours",
        target_value="increase",
        evidence_level="medium",
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    _, other_token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = client.post(
        f"/api/v1/daily-plan/actions/intervention.card.{card.id}/events",
        headers=other_headers,
        json={"event_type": "completed"},
    )

    assert resp.status_code == 404
