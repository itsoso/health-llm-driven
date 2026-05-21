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
