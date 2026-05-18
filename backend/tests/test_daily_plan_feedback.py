"""Daily Plan action feedback protocol tests."""

from datetime import date


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
