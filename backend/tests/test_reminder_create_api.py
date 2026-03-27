"""提醒创建 API 测试"""
import pytest
from datetime import datetime, timedelta
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
