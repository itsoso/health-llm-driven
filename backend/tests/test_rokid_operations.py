from tests.conftest import create_authenticated_user

from app.models.write_intent import WriteIntent


def test_create_rokid_operation_append_event_and_read_timeline(client, auth_user_and_headers):
    user, headers = auth_user_and_headers

    create_res = client.post(
        "/api/v1/devices/rokid/operations",
        headers=headers,
        json={
            "operation_id": "rokid-op-food-001",
            "type": "capture_food",
            "primary_surface": "rokid_glasses",
            "state": "queued",
            "meta": {"route": "cxrl_customview"},
            "entity_refs": {"meal_session_id": 42},
        },
    )

    assert create_res.status_code == 201
    operation = create_res.json()
    assert operation["operation_id"] == "rokid-op-food-001"
    assert operation["user_id"] == user.id
    assert operation["type"] == "capture_food"
    assert operation["state"] == "queued"
    assert operation["primary_surface"] == "rokid_glasses"
    assert operation["entity_refs"] == {"meal_session_id": 42}

    event_res = client.post(
        "/api/v1/devices/rokid/operations/rokid-op-food-001/events",
        headers=headers,
        json={
            "event_type": "capture_requested",
            "phase": "photo",
            "severity": "info",
            "state": "running",
            "message": "Rokid photo capture requested",
            "payload": {
                "source": "rokid_glasses",
                "image_sha256": "a" * 64,
                "has_base64": False,
            },
        },
    )

    assert event_res.status_code == 201
    event = event_res.json()
    assert event["operation_id"] == "rokid-op-food-001"
    assert event["event_type"] == "capture_requested"
    assert event["payload"]["image_sha256"] == "a" * 64

    timeline_res = client.get(
        "/api/v1/devices/rokid/operations/rokid-op-food-001",
        headers=headers,
    )

    assert timeline_res.status_code == 200
    timeline = timeline_res.json()
    assert timeline["operation"]["state"] == "running"
    assert timeline["operation"]["entity_refs"]["meal_session_id"] == 42
    assert timeline["operation"]["entity_refs"]["client_event_ids"] == [event["id"]]
    assert [item["event_type"] for item in timeline["events"]] == ["capture_requested"]


def test_rokid_operation_update_preserves_write_intent_when_omitted(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    write_intent = WriteIntent(
        user_id=user.id,
        kind="diet_draft_confirm",
        title="Confirm Rokid food draft",
        source="rokid_glasses",
    )
    db.add(write_intent)
    db.commit()
    db.refresh(write_intent)

    create_res = client.post(
        "/api/v1/devices/rokid/operations",
        headers=headers,
        json={
            "operation_id": "rokid-op-write-intent-001",
            "type": "capture_food",
            "state": "running",
            "write_intent_id": write_intent.id,
        },
    )
    assert create_res.status_code == 201

    update_res = client.post(
        "/api/v1/devices/rokid/operations",
        headers=headers,
        json={
            "operation_id": "rokid-op-write-intent-001",
            "type": "capture_food",
            "state": "succeeded",
            "summary": "Food draft submitted",
        },
    )
    assert update_res.status_code == 201
    assert update_res.json()["write_intent_id"] == write_intent.id


def test_rokid_operation_event_payload_backfills_domain_entity_refs(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    create_res = client.post(
        "/api/v1/devices/rokid/operations",
        headers=headers,
        json={
            "operation_id": "rokid-op-food-entity-refs-001",
            "type": "capture_food",
            "state": "running",
        },
    )
    assert create_res.status_code == 201

    event_res = client.post(
        "/api/v1/devices/rokid/operations/rokid-op-food-entity-refs-001/events",
        headers=headers,
        json={
            "event_type": "food_draft_submitted",
            "phase": "draft",
            "severity": "pass",
            "state": "succeeded",
            "message": "Food visual draft submitted",
            "payload": {
                "capture_source": "rokid_glasses",
                "visual_input_event_id": 77,
                "write_intent_id": 88,
                "target_type": "diet_draft",
                "target_id": 99,
                "diet_record_id": None,
            },
        },
    )
    assert event_res.status_code == 201

    timeline_res = client.get(
        "/api/v1/devices/rokid/operations/rokid-op-food-entity-refs-001",
        headers=headers,
    )
    assert timeline_res.status_code == 200
    refs = timeline_res.json()["operation"]["entity_refs"]
    assert refs["client_event_ids"] == [event_res.json()["id"]]
    assert refs["visual_input_event_ids"] == [77]
    assert refs["write_intent_ids"] == [88]
    assert refs["target_refs"] == [{"target_type": "diet_draft", "target_id": 99}]
    assert "diet_record_ids" not in refs


def test_rokid_diagnostics_upload_is_tied_to_operation_and_rejects_raw_media(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    client.post(
        "/api/v1/devices/rokid/operations",
        headers=headers,
        json={
            "operation_id": "rokid-op-diagnostics-001",
            "type": "voice_command",
        },
    )

    ok_res = client.post(
        "/api/v1/devices/rokid/diagnostics",
        headers=headers,
        json={
            "operation_id": "rokid-op-diagnostics-001",
            "summary": "audio stream missing, phone fallback active",
            "diagnostics": {
                "build": 184,
                "ble_connected": False,
                "audio": {"chunks": 0, "bytes": 0},
                "photo": {"has_base64": False, "has_sha256": False},
            },
        },
    )

    assert ok_res.status_code == 201
    diagnostic_event = ok_res.json()
    assert diagnostic_event["event_type"] == "diagnostic_snapshot"
    assert diagnostic_event["payload"]["diagnostics"]["audio"]["chunks"] == 0

    timeline_res = client.get(
        "/api/v1/devices/rokid/operations/rokid-op-diagnostics-001",
        headers=headers,
    )
    assert timeline_res.status_code == 200
    assert timeline_res.json()["operation"]["entity_refs"]["client_event_ids"] == [diagnostic_event["id"]]

    raw_media_res = client.post(
        "/api/v1/devices/rokid/diagnostics",
        headers=headers,
        json={
            "operation_id": "rokid-op-diagnostics-001",
            "summary": "should be rejected",
            "diagnostics": {
                "photo_base64": "not-allowed",
            },
        },
    )

    assert raw_media_res.status_code == 422


def test_rokid_operations_are_user_scoped(client, db, auth_user_and_headers):
    _, owner_headers = auth_user_and_headers
    _, other_token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    create_res = client.post(
        "/api/v1/devices/rokid/operations",
        headers=owner_headers,
        json={
            "operation_id": "rokid-op-private-001",
            "type": "pushup_session",
        },
    )
    assert create_res.status_code == 201

    read_res = client.get(
        "/api/v1/devices/rokid/operations/rokid-op-private-001",
        headers=other_headers,
    )
    assert read_res.status_code == 404

    append_res = client.post(
        "/api/v1/devices/rokid/operations/rokid-op-private-001/events",
        headers=other_headers,
        json={
            "event_type": "custom_view_opened",
            "severity": "info",
        },
    )
    assert append_res.status_code == 404
