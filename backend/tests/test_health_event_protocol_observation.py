"""HealthEvent -> HealthProtocol 自动观测闭环。

规划目标:Apple Watch/Garmin/Ring 等可穿戴识别到高置信度运动后,不再只记一条
HealthEvent,而是自动把对应的训练协议打成 auto_observed,减少用户手动打点。
"""
from app.models.health_protocol import HealthProtocolEvent


def _create_training_protocol(client, headers, **overrides):
    payload = {
        "domain": "training",
        "name": "到公司后俯卧撑 20 个",
        "mechanism": "passive_device",
        "cadence": "daily",
        "time_window": "morning",
        "completion_mode": "auto_observed",
        "can_default_complete": False,
    }
    payload.update(overrides)
    r = client.post("/api/v1/protocols", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _create_event_source(client, headers, protocol_id, *, threshold=0.8, device_id="watch-pushups"):
    r = client.post(
        "/api/v1/health-events/sources",
        headers=headers,
        json={
            "source_type": "api_webhook",
            "device_id": device_id,
            "name": "Apple Watch micro movement",
            "event_type": "exercise",
            "config": {"health_protocol_id": protocol_id},
            "auto_confirm_threshold": threshold,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_high_confidence_wearable_event_auto_observes_linked_training_protocol(
    client, auth_user_and_headers, db
):
    user, headers = auth_user_and_headers
    protocol_id = _create_training_protocol(client, headers)
    _create_event_source(client, headers, protocol_id)

    r = client.post(
        "/api/v1/health-events/ingest",
        headers=headers,
        json={
            "event_type": "exercise",
            "source": "api",
            "source_device_id": "watch-pushups",
            "raw_data": {"activity": "pushups", "reps": 20},
        },
    )

    assert r.status_code == 200, r.text
    event = r.json()
    assert event["status"] == "auto_confirmed"
    assert event["target_record_type"] == "health_protocol_events"

    protocol_events = db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.user_id == user.id,
        HealthProtocolEvent.protocol_id == protocol_id,
    ).all()
    assert len(protocol_events) == 1
    observed = protocol_events[0]
    assert observed.status == "auto_observed"
    assert observed.track == "protocol"
    assert observed.value["observed_from"] == "health_event"
    assert observed.value["health_event_id"] == event["id"]
    assert observed.value["confidence"] >= 0.8

    today = client.get("/api/v1/protocols/today", headers=headers).json()
    row = next(item for item in today if item["protocol_id"] == protocol_id)
    assert row["today_status"] == "auto_observed"

    watch = client.get("/api/v1/watch/summary", headers=headers).json()
    assert watch["agenda"]["pending"] == 0
    assert watch["top_action"] is None


def test_low_confidence_event_does_not_auto_observe_protocol(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    protocol_id = _create_training_protocol(client, headers)
    _create_event_source(client, headers, protocol_id, device_id="voice-pushups")

    r = client.post(
        "/api/v1/health-events/ingest",
        headers=headers,
        json={
            "event_type": "exercise",
            "source": "voice",
            "source_device_id": "voice-pushups",
            "raw_data": {"activity": "pushups", "reps": 20},
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    assert db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.user_id == user.id,
        HealthProtocolEvent.protocol_id == protocol_id,
    ).count() == 0


def test_event_source_protocol_link_cannot_observe_another_users_protocol(
    client, auth_user_and_headers, db
):
    from tests.conftest import create_authenticated_user

    user_a, headers_a = auth_user_and_headers
    _, token_b = create_authenticated_user(db)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    protocol_b = _create_training_protocol(client, headers_b)

    _create_event_source(client, headers_a, protocol_b, device_id="malicious-link")
    r = client.post(
        "/api/v1/health-events/ingest",
        headers=headers_a,
        json={
            "event_type": "exercise",
            "source": "api",
            "source_device_id": "malicious-link",
            "raw_data": {"activity": "pushups", "reps": 20},
        },
    )

    assert r.status_code == 200, r.text
    assert db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.user_id != user_a.id,
        HealthProtocolEvent.protocol_id == protocol_b,
    ).count() == 0
