from datetime import datetime, timezone

from tests.conftest import create_authenticated_user


def test_create_pushup_session_returns_one_time_ingest_token(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    res = client.post(
        "/api/v1/devices/rokid/pushup-sessions",
        json={"target_reps": 20, "source_device": "rokid_glasses_ultra"},
        headers=headers,
    )

    assert res.status_code == 201
    body = res.json()
    assert body["id"] > 0
    assert body["user_id"] == user.id
    assert body["target_reps"] == 20
    assert body["status"] == "active"
    assert body["source_device"] == "rokid_glasses_ultra"
    assert body["ingest_token"]
    assert body["ingest_token"] in body["open_url"]
    assert body["ingest_url"].endswith(f"/devices/rokid/pushup-sessions/{body['id']}/events")
    assert body["events_url"].endswith(f"/devices/rokid/pushup-sessions/{body['id']}/events")

    from app.models.rokid_pushup import RokidPushupSession

    row = db.query(RokidPushupSession).filter_by(id=body["id"]).one()
    assert row.user_id == user.id
    assert row.ingest_token_hash != body["ingest_token"]
    assert len(row.ingest_token_hash) == 64


def test_glasses_can_ingest_pose_events_and_owner_can_poll(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    create_res = client.post(
        "/api/v1/devices/rokid/pushup-sessions",
        json={"target_reps": 12},
        headers=headers,
    )
    session = create_res.json()

    bad_res = client.post(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/events",
        headers={"X-Reva-Rokid-Session-Token": "wrong-token"},
        json={
            "event_type": "pose",
            "phase": "down",
            "elbow_angle_deg": 84,
            "visibility": 0.94,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert bad_res.status_code == 403

    event_res = client.post(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/events",
        headers={"X-Reva-Rokid-Session-Token": session["ingest_token"]},
        json={
            "event_type": "pose",
            "phase": "down",
            "reps": 0,
            "elbow_angle_deg": 84,
            "shoulder_hip_ankle_angle_deg": 174,
            "visibility": 0.94,
            "quality_score": 91,
            "payload": {"model": "glasses_pose_v1", "frame_id": "f-1"},
        },
    )
    assert event_res.status_code == 201
    event = event_res.json()
    assert event["id"] > 0
    assert event["session_id"] == session["id"]
    assert event["event_type"] == "pose"
    assert event["phase"] == "down"
    assert event["elbow_angle_deg"] == 84
    assert event["payload"]["model"] == "glasses_pose_v1"

    poll_res = client.get(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/events",
        headers=headers,
    )
    assert poll_res.status_code == 200
    assert [e["id"] for e in poll_res.json()["events"]] == [event["id"]]

    poll_after_res = client.get(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/events?after_id={event['id']}",
        headers=headers,
    )
    assert poll_after_res.status_code == 200
    assert poll_after_res.json()["events"] == []


def test_glasses_can_ingest_session_state_events(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    create_res = client.post(
        "/api/v1/devices/rokid/pushup-sessions",
        json={"target_reps": 12},
        headers=headers,
    )
    session = create_res.json()

    event_res = client.post(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/events",
        headers={"X-Reva-Rokid-Session-Token": session["ingest_token"]},
        json={
            "event_type": "session_state",
            "payload": {
                "state": "session_ready",
                "message": "Reva session #7",
                "detail": "target_reps=20",
                "session_id": session["id"],
            },
        },
    )

    assert event_res.status_code == 201
    event = event_res.json()
    assert event["event_type"] == "session_state"
    assert event["payload"]["state"] == "session_ready"
    assert event["payload"]["session_id"] == session["id"]


def test_pushup_session_events_are_user_scoped(client, db, auth_user_and_headers):
    _, owner_headers = auth_user_and_headers
    _, other_token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {other_token}"}
    create_res = client.post(
        "/api/v1/devices/rokid/pushup-sessions",
        json={"target_reps": 20},
        headers=owner_headers,
    )
    session_id = create_res.json()["id"]

    res = client.get(
        f"/api/v1/devices/rokid/pushup-sessions/{session_id}/events",
        headers=other_headers,
    )

    assert res.status_code == 404
