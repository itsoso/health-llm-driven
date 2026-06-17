"""餐后散步窗 JITAI 降级 MVP。

记午/晚餐后生成一次性 walk 协议,进 Watch nudge,用户腕上一键完成后
落真实 ExerciseRecord。安全告警优先于行为 nudge。
"""
from datetime import date

from app.models.anomaly_alert import AnomalyAlert
from app.models.daily_health import DietRecord, ExerciseRecord
from app.models.health_protocol import HealthProtocol, HealthProtocolEvent
from app.services import watch_summary as watch_summary_service


def _diet_payload(meal_type: str, *, food_items: str = "鸡胸肉,糙米,青菜") -> dict:
    return {
        "record_date": date.today().isoformat(),
        "meal_type": meal_type,
        "food_items": food_items,
        "calories": 530,
        "protein": 40,
    }


def _post_diet(client, headers, meal_type: str, *, food_items: str = "鸡胸肉,糙米,青菜"):
    return client.post(
        "/api/v1/diet/records",
        headers=headers,
        json=_diet_payload(meal_type, food_items=food_items),
    )


def _postmeal_walk_protocols(db, user_id: int):
    return db.query(HealthProtocol).filter(
        HealthProtocol.user_id == user_id,
        HealthProtocol.domain == "exercise",
        HealthProtocol.source_model == "exercise_records",
    ).order_by(HealthProtocol.id).all()


def test_lunch_creates_one_due_postmeal_walk_protocol(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers

    r = _post_diet(client, headers, "lunch")

    assert r.status_code == 200, r.text
    protocols = _postmeal_walk_protocols(db, user.id)
    assert len(protocols) == 1
    walk = protocols[0]
    assert walk.name == "餐后轻松步行 20 分钟"
    assert walk.cadence == "event_triggered"
    assert walk.time_window in {"noon", "afternoon"}
    assert walk.can_default_complete is False
    assert walk.implied_quantity["exercise_type"] == "walk"
    assert walk.implied_quantity["duration_min"] == 20
    assert walk.implied_quantity["trigger_meal_type"] == "lunch"
    assert walk.implied_quantity["trigger_date"] == date.today().isoformat()

    today = client.get("/api/v1/protocols/today", headers=headers).json()
    row = next(item for item in today if item["protocol_id"] == walk.id)
    assert row["is_due_today"] is True
    assert row["today_status"] == "pending"

    watch = client.get("/api/v1/watch/summary", headers=headers).json()
    assert any(item["kind"] == "exercise" and item["action_id"] for item in watch["due_items"])


def test_postmeal_walk_protocol_is_idempotent_per_meal_slot(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers

    assert _post_diet(client, headers, "lunch").status_code == 200
    assert _post_diet(client, headers, "lunch", food_items="牛肉饭").status_code == 200
    assert _post_diet(client, headers, "breakfast").status_code == 200
    assert _post_diet(client, headers, "snack").status_code == 200
    assert _post_diet(client, headers, "dinner").status_code == 200

    protocols = _postmeal_walk_protocols(db, user.id)
    assert len(protocols) == 2
    assert {p.implied_quantity["trigger_meal_type"] for p in protocols} == {"lunch", "dinner"}


def test_postmeal_hook_failure_does_not_block_diet_record(
    client, auth_user_and_headers, db, monkeypatch
):
    import app.services.health_protocol_service as protocol_service

    user, headers = auth_user_and_headers

    def _boom(*_args, **_kwargs):
        raise RuntimeError("postmeal hook failed")

    monkeypatch.setattr(protocol_service, "create_postmeal_walk_protocol", _boom, raising=False)

    r = _post_diet(client, headers, "lunch")

    assert r.status_code == 200, r.text
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 1
    assert _postmeal_walk_protocols(db, user.id) == []


def test_watch_complete_postmeal_walk_writes_exercise_once(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    assert _post_diet(client, headers, "dinner").status_code == 200
    walk = _postmeal_walk_protocols(db, user.id)[0]
    action_id = f"agenda-health_protocol-{walk.id}"

    r1 = client.post(f"/api/v1/watch/actions/{action_id}/complete", headers=headers)
    r2 = client.post(f"/api/v1/watch/actions/{action_id}/complete", headers=headers)

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["written"] == "exercise_record"
    records = db.query(ExerciseRecord).filter(ExerciseRecord.user_id == user.id).all()
    assert len(records) == 1
    exercise = records[0]
    assert exercise.exercise_type == "walk"
    assert exercise.duration == 20
    assert exercise.intensity == "easy"
    assert "餐后散步" in (exercise.notes or "")

    events = db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.user_id == user.id,
        HealthProtocolEvent.protocol_id == walk.id,
    ).all()
    assert len(events) == 1
    assert events[0].status == "completed"


def test_watch_push_exercise_pending_respects_safety_and_frequency_gate(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    item = {
        "type": "exercise",
        "title": "餐后轻松步行 20 分钟",
        "status": "pending",
        "priority": 65,
        "time_window": "evening",
        "source": {"object_type": "health_protocol", "object_id": 99},
    }
    monkeypatch.setattr(
        watch_summary_service.agenda_service,
        "today",
        lambda _db, _user_id, **_kwargs: {"agenda_date": date.today().isoformat(), "count": 1, "items": [item]},
    )
    monkeypatch.setattr(
        watch_summary_service.proactive_coordinator,
        "can_notify_proactively",
        lambda _db, _user_id, tier="P1": True,
    )

    watch = watch_summary_service.build_watch_summary(db, user.id)
    assert any(push["kind"] == "exercise" and push["tier"] == "P1" for push in watch["push_items"])

    db.add(AnomalyAlert(
        user_id=user.id,
        alert_type="bp_critical",
        severity="critical",
        metric_name="blood_pressure",
        detection_date=date.today(),
        message="血压异常",
        acknowledged=False,
        is_suppressed=False,
    ))
    db.commit()

    suppressed = watch_summary_service.build_watch_summary(db, user.id)
    assert not any(push["kind"] == "exercise" for push in suppressed["push_items"])

    monkeypatch.setattr(
        watch_summary_service.proactive_coordinator,
        "can_notify_proactively",
        lambda _db, _user_id, tier="P1": False,
    )
    db.query(AnomalyAlert).delete()
    db.commit()

    budget_blocked = watch_summary_service.build_watch_summary(db, user.id)
    assert not any(push["kind"] == "exercise" for push in budget_blocked["push_items"])
