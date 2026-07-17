"""提醒创建 API 测试"""
import pytest
from datetime import datetime, timedelta
from app.models.smart_reminder import SmartReminder
from app.models.user import User


@pytest.fixture
def test_user(db):
    user = User(
        username="reminderuser",
        email="reminder@example.com",
        hashed_password="hashed_password",
        name="提醒测试用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


class TestReminderCreateAPI:

    def test_create_reminder(self, client, auth_headers):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT09:00:00+08:00")
        response = client.post(
            "/api/v1/reminders/me",
            json={
                "title": "吃药",
                "message": "饭后服用维生素D",
                "remind_at": tomorrow,
                "priority": "normal",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "吃药"
        assert data["status"] == "pending"
        assert "id" in data
        assert data["delivery_status"]["agent_claim"] == "created_not_device_delivered"
        assert data["delivery_status"]["iphone_notification"]["status"] == "will_attempt_when_due"
        assert data["delivery_status"]["watch"]["route"] == "watch_summary_due_item"
        assert data["delivery_status"]["watch"]["delivery_confirmed"] is False

    def test_create_reminder_minimal(self, client, auth_headers):
        tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
        response = client.post(
            "/api/v1/reminders/me",
            json={"title": "测试", "remind_at": tomorrow},
            headers=auth_headers,
        )
        assert response.status_code == 201

    def test_create_reminder_past_time(self, client, auth_headers):
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT09:00:00+08:00")
        response = client.post(
            "/api/v1/reminders/me",
            json={"title": "过期提醒", "remind_at": past},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_create_reminder_invalid_priority(self, client, auth_headers):
        tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
        response = client.post(
            "/api/v1/reminders/me",
            json={"title": "测试", "remind_at": tomorrow, "priority": "invalid"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_create_recurring_reminder_past_ok(self, client, auth_headers):
        """Recurring reminders allow past remind_at"""
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT09:00:00+08:00")
        response = client.post(
            "/api/v1/reminders/me",
            json={
                "title": "每日提醒",
                "remind_at": past,
                "recurrence": "daily",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201

    def test_get_reminders(self, client, auth_headers):
        response = client.get("/api/v1/reminders/me", headers=auth_headers)
        assert response.status_code == 200

    def test_no_auth(self, client):
        response = client.post(
            "/api/v1/reminders/me",
            json={"title": "test", "remind_at": "2026-12-01T09:00:00+08:00"},
        )
        assert response.status_code in (401, 403)

    def test_create_daily_window_is_complete_and_idempotent(
        self,
        client,
        auth_headers,
        db,
        test_user,
    ):
        payload = {
            "title": "定时饮水提醒",
            "message": "少量多次饮水",
            "start_time": "09:00",
            "end_time": "20:00",
            "interval_minutes": 90,
            "recurrence": "daily",
        }

        first = client.post(
            "/api/v1/reminders/me/window",
            json=payload,
            headers=auth_headers,
        )
        assert first.status_code == 201
        first_data = first.json()
        assert first_data["status"] == "scheduled"
        assert first_data["resource_type"] == "smart_reminder"
        assert first_data["delivery_status"]["agent_claim"] == "created_not_device_delivered"
        assert first_data["delivery_status"]["iphone_notification"]["status"] == "will_attempt_when_due"
        assert first_data["delivery_status"]["watch"]["route"] == "watch_summary_due_item"
        assert first_data["delivery_status"]["watch"]["delivery_confirmed"] is False
        assert first_data["created_count"] == 8
        assert first_data["existing_count"] == 0
        assert first_data["times"] == [
            "09:00", "10:30", "12:00", "13:30",
            "15:00", "16:30", "18:00", "19:30",
        ]
        assert len(first_data["record_ids"]) == 8

        second = client.post(
            "/api/v1/reminders/me/window",
            json=payload,
            headers=auth_headers,
        )
        assert second.status_code == 201
        second_data = second.json()
        assert second_data["created_count"] == 0
        assert second_data["existing_count"] == 8
        assert second_data["record_ids"] == first_data["record_ids"]

        assert db.query(SmartReminder).filter(
            SmartReminder.user_id == test_user.id,
            SmartReminder.title == payload["title"],
            SmartReminder.status == "pending",
        ).count() == 8

    def test_create_daily_window_never_reuses_another_users_reminder(
        self,
        client,
        auth_headers,
        db,
        test_user,
    ):
        other_user = User(
            username="other-reminder-user",
            email="other-reminder@example.com",
            hashed_password="hashed_password",
            name="另一位用户",
            is_active=True,
            is_approved=True,
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)
        db.add(SmartReminder(
            user_id=other_user.id,
            title="定时饮水提醒",
            message="少量多次饮水",
            remind_at=datetime.now().replace(hour=9, minute=0, second=0, microsecond=0),
            priority="normal",
            recurrence="daily",
            status="pending",
        ))
        db.commit()

        response = client.post(
            "/api/v1/reminders/me/window",
            json={
                "title": "定时饮水提醒",
                "message": "少量多次饮水",
                "start_time": "09:00",
                "end_time": "10:30",
                "interval_minutes": 90,
                "recurrence": "daily",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        assert response.json()["created_count"] == 2
        assert db.query(SmartReminder).filter(
            SmartReminder.user_id == test_user.id,
            SmartReminder.title == "定时饮水提醒",
        ).count() == 2
