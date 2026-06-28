"""Daily Plan action feedback protocol tests."""

from datetime import date, datetime, timedelta, timezone

from tests.conftest import create_authenticated_user


def _prediction_context(metric: str = "waist_cm"):
    return {
        "id": f"personal_prediction:cycle:1:{metric}",
        "prediction_type": "intervention_cycle_projection",
        "metric": metric,
        "domain": "metabolic_health",
        "horizon_days": 7,
        "baseline": 96.0,
        "unit": "cm",
        "expected_signal": {"metric": metric, "direction": "down", "expected_delta": -0.5},
        "confidence": "medium",
        "uncertainty": {"level": "medium", "drivers": ["n_of_1_observational_cycle"]},
        "evidence_tier": "personal_observation",
        "source_model": "phase1-hbayes-v1",
        "model_version": "personal_prediction_v1",
        "claim_boundary": "观察性预测, 不证明单个行动造成指标变化。",
        "review_hint": "到复测窗口后用实际指标回测。",
    }


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


def test_daily_plan_feedback_stores_standard_prediction_record(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    from app.api import daily_plan

    today = date.today()
    prediction = _prediction_context()
    monkeypatch.setattr(daily_plan, "build_daily_operating_plan", lambda db, uid, plan_date=None: {
        "id": 123,
        "plan_date": today.isoformat(),
        "actions": [
            {
                "action_key": "movement.moderate_activity",
                "domain": "movement",
                "title": "累计 35-45 分钟中等强度活动",
                "metric_key": "waist_cm",
                "personal_prediction_context": prediction,
            },
        ],
    }, raising=False)

    resp = client.post(
        "/api/v1/daily-plan/me/actions/movement.moderate_activity/feedback",
        headers=headers,
        json={"status": "done", "reason": "已完成"},
    )

    assert resp.status_code == 200
    from app.models.intervention_event import InterventionEvent

    row = db.query(InterventionEvent).filter(InterventionEvent.user_id == user.id).one()
    record = row.action_snapshot["prediction_record"]
    assert record["id"] == "personal_prediction:cycle:1:waist_cm"
    assert record["source"] == "phase1-hbayes-v1"
    assert record["source_model"] == "phase1-hbayes-v1"
    assert record["prediction_type"] == "intervention_cycle_projection"
    assert record["metric"] == "waist_cm"
    assert record["expected_signal"]["direction"] == "down"
    assert record["confidence"] == "medium"
    assert record["uncertainty"]["level"] == "medium"
    assert record["evidence_tier"] == "personal_observation"
    assert record["model_version"] == "personal_prediction_v1"
    assert record["attached_to"]["object_type"] == "daily_plan_action"
    assert record["attached_to"]["object_id"] == "movement.moderate_activity"
    assert "不证明" in record["claim_boundary"]


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


def test_daily_plan_action_event_stores_standard_prediction_record(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    from app.api import daily_plan

    today = date.today()
    monkeypatch.setattr(daily_plan, "build_daily_operating_plan", lambda db, uid, plan_date=None: {
        "id": 124,
        "plan_date": today.isoformat(),
        "actions": [
            {
                "action_key": "movement.moderate_activity",
                "domain": "movement",
                "title": "累计 35-45 分钟中等强度活动",
                "metric_key": "waist_cm",
                "personal_prediction_context": _prediction_context(),
            },
        ],
    }, raising=False)

    resp = client.post(
        "/api/v1/daily-plan/actions/movement.moderate_activity/events",
        headers=headers,
        json={"event_type": "completed", "payload": {"source": "watch"}},
    )

    assert resp.status_code == 200
    from app.models.intervention_event import InterventionEvent

    row = db.query(InterventionEvent).filter(InterventionEvent.user_id == user.id).one()
    assert row.action_snapshot["event_payload"] == {"source": "watch"}
    assert row.action_snapshot["prediction_record"]["id"] == "personal_prediction:cycle:1:waist_cm"


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
