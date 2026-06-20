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


def test_ambient_audio_input_routes_movement_to_guided_task(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/audio-inputs",
        headers=headers,
        json={
            "intent": "movement",
            "transcript": "今天练什么",
            "source": "rokid_glasses",
            "device_type": "glasses",
            "confidence": 0.86,
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert event.intent == "movement"
    assert event.source == "rokid_glasses"
    assert body["recommended_next_action"] == {
        "type": "fetch_guided_movement",
        "method": "GET",
        "path": "/movement/guided-task?domain=strength",
    }


def test_rokid_voice_command_routes_food_photo_to_client_capture_and_audits_event(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/rokid-voice-commands",
        headers=headers,
        json={
            "transcript": "帮我拍一下这餐, 记录热量",
            "confidence": 0.91,
            "context": "rokid_health",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert body["event"]["id"] == event.id
    assert event.intent == "food"
    assert event.source == "rokid_glasses"
    assert event.device_type == "glasses"
    assert event.status == "processed"
    assert event.target_type == "rokid_voice_command"
    assert event.meta["command_intent"] == "food_photo"
    assert body["command"] == {
        "intent": "food_photo",
        "client_action": "capture_food_photo",
        "route": None,
        "voice_reply": "我来拍这餐, 识别后会生成待确认的热量和营养记录。",
        "display_text": "拍摄餐食并生成待确认饮食记录",
        "requires_confirmation": True,
        "safety_level": "health_l3",
        "parameters": {"visual_intent": "food_scan"},
        "recommended_next_action": {
            "type": "capture_food_photo",
            "method": "POST",
            "path": "/ambient/visual-inputs",
        },
    }


def test_rokid_voice_command_routes_current_meal_phrase_to_food_photo(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/rokid-voice-commands",
        headers=headers,
        json={
            "transcript": "记录这顿饭",
            "confidence": 0.88,
            "context": "rokid_health",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert event.intent == "food"
    assert event.meta["command_intent"] == "food_photo"
    assert body["command"]["intent"] == "food_photo"
    assert body["command"]["client_action"] == "capture_food_photo"


def test_rokid_voice_command_routes_pushup_start_to_pushup_coach(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/rokid-voice-commands",
        headers=headers,
        json={"transcript": "开始俯卧撑, 来一组二十个", "context": "rokid_health"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert event.intent == "movement"
    assert event.status == "processed"
    assert event.meta["command_intent"] == "pushup_start"
    assert body["command"]["intent"] == "pushup_start"
    assert body["command"]["client_action"] == "open_pushup_coach"
    assert body["command"]["route"] == "/rokid-pushup-coach"
    assert body["command"]["parameters"] == {"target_reps": 20}
    assert body["command"]["recommended_next_action"] == {
        "type": "start_rokid_pushup_session",
        "method": "POST",
        "path": "/devices/rokid/pushup-sessions",
    }


def test_rokid_voice_command_routes_exercise_guidance_to_guided_task(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/rokid-voice-commands",
        headers=headers,
        json={"transcript": "今天练什么, 指导我运动", "context": "rokid_health"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert event.intent == "movement"
    assert event.status == "processed"
    assert event.meta["command_intent"] == "exercise_guidance"
    assert body["command"]["intent"] == "exercise_guidance"
    assert body["command"]["client_action"] == "open_guided_task"
    assert body["command"]["route"] == "/guided-task?domain=strength&source=rokid_voice"
    assert body["command"]["recommended_next_action"] == {
        "type": "fetch_guided_movement",
        "method": "GET",
        "path": "/movement/guided-task?domain=strength",
    }


def test_rokid_voice_command_unknown_asks_for_clarification_without_client_side_write(client, db):
    from app.models.ambient_wearable import AudioInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/rokid-voice-commands",
        headers=headers,
        json={"transcript": "帮我订一杯咖啡", "context": "rokid_health"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(AudioInputEvent).filter(AudioInputEvent.user_id == user.id).one()
    assert event.intent == "note"
    assert event.status == "pending_clarification"
    assert event.meta["command_intent"] == "unknown"
    assert event.safety_result["routed"] is False
    assert body["command"]["intent"] == "unknown"
    assert body["command"]["client_action"] == "clarify"
    assert body["command"]["recommended_next_action"] is None


def test_rokid_visual_food_scan_records_visual_input_event(client, db):
    from app.models.ambient_wearable import VisualInputEvent

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/visual-inputs",
        headers=headers,
        json={
            "intent": "food_scan",
            "source": "rokid_glasses",
            "device_type": "glasses",
            "image_uri": "private://rokid/meal-001.jpg",
            "ocr_text": "牛肉面",
            "recognition_result": {
                "foods": [{"name": "牛肉面", "quantity": 1, "unit": "碗"}],
                "confidence": 0.76,
            },
            "confidence": 0.76,
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(VisualInputEvent).filter(VisualInputEvent.user_id == user.id).one()
    assert body["event"]["id"] == event.id
    assert event.intent == "food_scan"
    assert event.source == "rokid_glasses"
    assert event.device_type == "glasses"
    assert event.status == "pending_confirmation"
    assert event.privacy_class == "health_l3"
    assert event.ocr_text == "牛肉面"
    assert event.recognition_result["foods"][0]["name"] == "牛肉面"
    assert body["recommended_next_action"] == {
        "type": "confirm_food_draft",
        "method": "POST",
        "path": "/diet/records",
    }


def test_rokid_visual_food_scan_with_manual_confirm_does_not_autosave(client, db):
    from app.models.ambient_wearable import VisualInputEvent
    from app.models.daily_health import DietRecord

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/visual-inputs",
        headers=headers,
        json={
            "intent": "food_scan",
            "source": "rokid_glasses",
            "device_type": "glasses",
            "image_uri": "private://rokid/meal-002.jpg",
            "ocr_text": "牛肉面",
            "recognition_result": {
                "success": True,
                "foods": [
                    {
                        "name": "牛肉面",
                        "quantity": 1,
                        "unit": "碗",
                        "calories": 620,
                        "protein": 32,
                        "carbs": 78,
                        "fat": 20,
                        "fiber": 4,
                        "confidence": 0.76,
                    }
                ],
                "meal_type": "lunch",
                "total_calories": 620,
                "total_protein": 32,
                "total_carbs": 78,
                "total_fat": 20,
                "total_fiber": 4,
                "health_tips": "高盐餐后补水, 下餐增加蔬菜。",
            },
            "confidence": 0.76,
            "meta": {"manual_confirm_required": True},
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    event = db.query(VisualInputEvent).filter(VisualInputEvent.user_id == user.id).one()

    # R4: manual_confirm_required=True → 不自动落 DietRecord,只标待确认草稿,等用户在饮食页确认。
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 0
    assert event.status == "needs_confirmation"
    assert event.target_type == "diet_draft"
    assert body["event"]["target_type"] != "diet_record"
    assert event.safety_result.get("manual_confirmation_required") is True


def test_rokid_visual_food_scan_high_confidence_autosaves_diet_record(client, db):
    """没要求确认 + 高置信(>=0.9)才允许自动落库。"""
    from app.models.ambient_wearable import VisualInputEvent
    from app.models.daily_health import DietRecord

    user, headers = _auth(db)

    resp = client.post(
        "/api/v1/ambient/visual-inputs",
        headers=headers,
        json={
            "intent": "food_scan",
            "source": "rokid_glasses",
            "device_type": "glasses",
            "image_uri": "private://rokid/meal-003.jpg",
            "ocr_text": "牛肉面",
            "recognition_result": {
                "success": True,
                "foods": [
                    {
                        "name": "牛肉面",
                        "quantity": 1,
                        "unit": "碗",
                        "calories": 620,
                        "protein": 32,
                        "carbs": 78,
                        "fat": 20,
                        "fiber": 4,
                        "confidence": 0.95,
                    }
                ],
                "meal_type": "lunch",
                "total_calories": 620,
                "total_protein": 32,
                "total_carbs": 78,
                "total_fat": 20,
                "total_fiber": 4,
            },
            "confidence": 0.95,
        },
    )

    assert resp.status_code == 201, resp.text
    event = db.query(VisualInputEvent).filter(VisualInputEvent.user_id == user.id).one()
    record = db.query(DietRecord).filter(DietRecord.user_id == user.id).one()
    assert event.status == "processed"
    assert event.target_type == "diet_record"
    assert event.target_id == record.id
    assert record.food_name == "牛肉面"
    assert record.calories == 620
    assert record.ai_confidence == 0.95


def test_rokid_glance_cards_are_short_lived_and_user_scoped(client, db):
    from app.models.ambient_wearable import GlanceCard

    user, headers = _auth(db)
    other_user, _ = _auth(db)
    db.add(
        GlanceCard(
            user_id=other_user.id,
            surface="rokid_glasses",
            card_type="action_prompt",
            title="别人的卡片",
            body="不应该出现在当前用户列表",
        )
    )
    db.commit()

    create = client.post(
        "/api/v1/ambient/glance-cards",
        headers=headers,
        json={
            "surface": "rokid_glasses",
            "card_type": "action_prompt",
            "title": "补水",
            "body": "现在喝水 300ml",
            "priority": "normal",
            "action": {
                "label": "已完成",
                "kind": "client_event",
                "path": "/client-events",
            },
            "target_type": "health_agenda_item",
            "target_id": 42,
        },
    )

    assert create.status_code == 201, create.text
    created = create.json()
    assert created["surface"] == "rokid_glasses"
    assert len(created["title"]) <= 40
    assert len(created["body"]) <= 120

    listed = client.get("/api/v1/ambient/glance-cards?surface=rokid_glasses", headers=headers)
    assert listed.status_code == 200, listed.text
    cards = listed.json()
    assert [card["id"] for card in cards] == [created["id"]]


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
