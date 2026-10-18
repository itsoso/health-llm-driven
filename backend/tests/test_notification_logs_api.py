"""Notification logs API regression tests."""


def test_notification_logs_include_data_and_deep_link(client, db, auth_user_and_headers):
    from app.models.notification import NotificationLog

    user, headers = auth_user_and_headers
    db.add(NotificationLog(
        user_id=user.id,
        notification_type="workout_analysis",
        channel="ios_apns",
        title="跑后教练: 跑步 (2.9km · 20分钟)",
        content="指标 | 本次数 据 | 评价",
        status="sent",
        data={
            "deep_link": "/workout-detail?id=123",
            "kind": "workout_analysis",
            "workout_id": 123,
        },
        channels=[{"name": "ios_apns", "status": "sent"}],
    ))
    db.commit()

    r = client.get("/api/v1/notification/logs", headers=headers)

    assert r.status_code == 200
    log = r.json()["logs"][0]
    assert log["data"]["workout_id"] == 123
    assert log["deep_link"] == "/workout-detail?id=123"


def test_existing_protocol_reminder_history_has_read_only_agenda_link(client, db, auth_user_and_headers):
    from app.models.notification import NotificationLog
    from app.models.health_protocol import HealthProtocolEvent
    from tests.conftest import create_authenticated_user

    user, headers = auth_user_and_headers
    _, other_token = create_authenticated_user(db)
    payload = {"kind": "protocol", "category": "AGENDA_ACTION",
               "complete_ref": {"object_type": "health_protocol", "object_id": 42}}
    row = NotificationLog(user_id=user.id, notification_type="reminder", channel="ios_apns",
                          title="健康提醒", content="完成后确认", status="sent", data=payload)
    db.add(row)
    db.commit()
    before = db.query(HealthProtocolEvent).count()
    for _ in range(2):
        response = client.get("/api/v1/notification/logs", headers=headers)
        assert response.status_code == 200
        log = next(x for x in response.json()["logs"] if x["id"] == row.id)
        assert log["deep_link"] == "/agenda"
        assert log["data"] == payload
    db.refresh(row)
    assert row.data == payload  # compatibility projection, not a history rewrite
    assert db.query(HealthProtocolEvent).count() == before
    other = client.get("/api/v1/notification/logs", headers={"Authorization": f"Bearer {other_token}"})
    assert other.status_code == 200 and other.json()["logs"] == []


def test_history_preserves_explicit_links_and_does_not_infer_from_health_title(client, db, auth_user_and_headers):
    from app.models.notification import NotificationLog

    user, headers = auth_user_and_headers
    cases = [
        ({"kind": "protocol", "category": "AGENDA_ACTION", "deep_link": "/calendar"}, "/calendar"),
        ({"kind": "protocol", "category": "AGENDA_ACTION", "deeplink": "/calendar"}, "/calendar"),
        ({"kind": "unknown"}, None),
        ({}, None),
    ]
    expected = {}
    for payload, link in cases:
        row = NotificationLog(user_id=user.id, notification_type="reminder", channel="ios_apns",
                              title="健康提醒", content="合成提醒", status="sent", data=payload)
        db.add(row)
        db.flush()
        expected[row.id] = link or f"/notification-history?detailId={row.id}"
    db.commit()
    response = client.get("/api/v1/notification/logs", headers=headers)
    assert response.status_code == 200
    assert {x["id"]: x["deep_link"] for x in response.json()["logs"]} == expected
