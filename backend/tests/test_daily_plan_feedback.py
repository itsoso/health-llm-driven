"""Daily Plan action feedback protocol tests."""

from datetime import date, datetime, timedelta, timezone

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


def test_completed_daily_plan_action_is_removed_from_refreshed_plan(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    plan_resp = client.get("/api/v1/daily-plan/me", headers=headers)
    assert plan_resp.status_code == 200
    action = plan_resp.json()["actions"][0]
    action_key = action["action_key"]

    event_resp = client.post(
        f"/api/v1/daily-plan/actions/{action_key}/events",
        headers=headers,
        json={"event_type": "completed", "payload": {"source": "home"}},
    )
    assert event_resp.status_code == 200

    refreshed = client.get("/api/v1/daily-plan/me", headers=headers)
    assert refreshed.status_code == 200
    assert action_key not in [a["action_key"] for a in refreshed.json()["actions"]]


def test_daily_plan_progress_separates_completed_from_other_terminal_events(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    plan_resp = client.get("/api/v1/daily-plan/me", headers=headers)
    assert plan_resp.status_code == 200
    actions = plan_resp.json()["actions"]
    assert len(actions) >= 2
    completed_key = actions[0]["action_key"]
    skipped_key = actions[1]["action_key"]

    from app.models.intervention_event import InterventionEvent

    db.add_all([
        InterventionEvent(
            user_id=user.id,
            plan_date=date.today(),
            action_key=completed_key,
            action_domain=actions[0]["domain"],
            action_title=actions[0]["title"],
            feedback_status="completed",
            source="daily_plan",
            action_snapshot=actions[0],
        ),
        InterventionEvent(
            user_id=user.id,
            plan_date=date.today(),
            action_key=skipped_key,
            action_domain=actions[1]["domain"],
            action_title=actions[1]["title"],
            feedback_status="skipped",
            source="daily_plan",
            action_snapshot=actions[1],
        ),
    ])
    db.commit()

    refreshed = client.get("/api/v1/daily-plan/me", headers=headers)
    assert refreshed.status_code == 200
    body = refreshed.json()
    refreshed_keys = [a["action_key"] for a in body["actions"]]
    assert completed_key not in refreshed_keys
    assert skipped_key not in refreshed_keys

    progress = body["state_summary"]["action_progress"]
    assert progress["completed_count"] == 1
    assert progress["handled_count"] == 2
    assert progress["remaining_count"] == len(body["actions"])
    assert progress["completed_action_keys"] == [completed_key]
    assert set(progress["terminal_action_keys"]) == {completed_key, skipped_key}


def test_completed_intervention_action_syncs_source_card_and_disappears(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard

    card = ActionCard(
        user_id=user.id,
        title="跑后拉伸 10 分钟",
        content="跑后完成腿后侧和小腿拉伸。",
        status="active",
        is_visible=True,
        user_decision="accepted",
        priority=50,
        metric_key="custom",
        target_value="stretch_10m",
        evidence_level="medium",
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    action_key = f"intervention.card.{card.id}"
    plan_resp = client.get("/api/v1/daily-plan/me", headers=headers)
    assert plan_resp.status_code == 200
    assert action_key in [a["action_key"] for a in plan_resp.json()["actions"]]

    event_resp = client.post(
        f"/api/v1/daily-plan/actions/{action_key}/events",
        headers=headers,
        json={"event_type": "completed", "payload": {"source": "home"}},
    )
    assert event_resp.status_code == 200

    db.refresh(card)
    assert card.status == "completed"
    assert card.completed_at is not None

    refreshed = client.get("/api/v1/daily-plan/me", headers=headers)
    assert refreshed.status_code == 200
    assert action_key not in [a["action_key"] for a in refreshed.json()["actions"]]


def test_expired_intervention_card_is_archived_and_not_shown(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard

    card = ActionCard(
        user_id=user.id,
        title="已过期的补剂行动",
        content="这个行动窗口已经结束。",
        status="active",
        is_visible=True,
        user_decision="accepted",
        priority=100,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        metric_key="custom",
        target_value="expired",
        evidence_level="medium",
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    resp = client.get("/api/v1/daily-plan/me", headers=headers)
    assert resp.status_code == 200
    assert f"intervention.card.{card.id}" not in [a["action_key"] for a in resp.json()["actions"]]

    db.refresh(card)
    assert card.status == "archived"
    assert card.is_visible is False
