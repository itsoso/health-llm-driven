import uuid
from datetime import datetime, timedelta, timezone

from app.models.user import User
from app.models.write_intent import WriteIntent
from app.models.smart_reminder import SmartReminder


def _auth(db):
    user = User(
        username=f"ambient_{uuid.uuid4().hex[:8]}",
        email=f"ambient_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="ambient",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.auth import auth_service

    return user, {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


def test_diet_voice_parse_records_audio_input_event(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/diet/voice/parse",
        headers=headers,
        json={
            "raw_text": "午餐吃了鸡胸肉沙拉",
            "source": "apple_watch",
            "device_type": "watch",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert event.intent == "food"
    assert event.source == "apple_watch"
    assert event.device_type == "watch"
    assert event.transcript == "午餐吃了鸡胸肉沙拉"
    assert event.status == "pending_confirmation"
    assert event.target_type == "diet_voice_draft"
    assert event.confidence == body["confidence"]
    assert event.meta["parser_version"] == body["parser_version"]


def test_watch_symptom_records_audio_input_event_with_safety_summary(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/watch/symptoms",
        headers=headers,
        json={"text": "有点反酸,胃不舒服"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert event.intent == "symptom"
    assert event.source == "apple_watch"
    assert event.device_type == "watch"
    assert event.transcript == "有点反酸,胃不舒服"
    assert event.status == "processed"
    assert event.target_type == "symptom_entry"
    assert event.target_id == body["symptom_id"]
    assert event.safety_result["evaluation_failed"] is False
    assert event.safety_result["alerts_count"] == len(body["alerts"])


def test_ambient_audio_input_routes_food_to_existing_draft_endpoint(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/audio-inputs",
        headers=headers,
        json={
            "intent": "food",
            "transcript": "晚餐吃了牛肉面",
            "source": "airpods",
            "device_type": "earbuds",
            "confidence": 0.82,
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert body["event"]["id"] == event.id
    assert body["event"]["status"] == "pending_confirmation"
    assert body["recommended_next_action"] == {
        "type": "parse_food_draft",
        "method": "POST",
        "path": "/diet/voice/parse",
    }


def test_hearing_health_task_creates_idempotent_manual_confirm_write_intent(client, db):
    from app.models.ambient_wearable import HearingHealthTask

    user, headers = _auth(db)
    due_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    payload = {
        "task_type": "hearing_test",
        "reason": "最近会议听清楚更费力",
        "source": "airpods",
        "due_at": due_at,
    }

    first = client.post("/api/v1/ambient/hearing/tasks", headers=headers, json=payload)
    second = client.post("/api/v1/ambient/hearing/tasks", headers=headers, json=payload)

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    first_body = first.json()
    second_body = second.json()
    assert first_body["task"]["id"] == second_body["task"]["id"]
    assert first_body["write_intent"]["id"] == second_body["write_intent"]["id"]

    task = db.query(HearingHealthTask).filter(HearingHealthTask.user_id == user.id).one()
    intent = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one()
    assert task.write_intent_id == intent.id
    assert intent.kind == "hearing_health_task"
    assert intent.trust_tier == "manual_confirm"
    assert intent.target_type == "hearing_health_task"
    assert intent.target_id == task.id


def test_confirm_hearing_health_write_intent_creates_reminder(client, db):
    from app.models.ambient_wearable import HearingHealthTask

    user, headers = _auth(db)
    create = client.post(
        "/api/v1/ambient/hearing/tasks",
        headers=headers,
        json={"task_type": "noise_review", "reason": "通勤噪音暴露偏高"},
    )
    assert create.status_code == 201, create.text
    intent_id = create.json()["write_intent"]["id"]

    confirm = client.post(f"/api/v1/write-intents/{intent_id}/confirm", headers=headers)

    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "executed"
    assert confirm.json()["executed_ref"].startswith("smart_reminder:")
    task = db.query(HearingHealthTask).filter(HearingHealthTask.user_id == user.id).one()
    reminder = db.query(SmartReminder).filter(SmartReminder.user_id == user.id).one()
    assert reminder.extra_data["kind"] == "hearing_health_task"
    assert reminder.extra_data["target_id"] == task.id
