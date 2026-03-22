"""交互反馈 API 测试"""
import pytest
from app.models.user import User


@pytest.fixture
def test_user(db):
    user = User(
        username="feedbackuser",
        email="feedback@example.com",
        hashed_password="hashed_password",
        name="反馈测试用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db):
    user = User(
        username="adminuser",
        email="admin@example.com",
        hashed_password="hashed_password",
        name="管理员",
        is_active=True,
        is_approved=True,
        is_admin=True,
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


@pytest.fixture
def admin_headers(client, admin_user):
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


class TestFeedbackAPI:

    def test_submit_thumbs_up(self, client, auth_headers):
        """测试提交 👍 评分"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "chat",
                "conversation_id": 1,
                "message_id": 10,
                "rating": 5,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 5
        assert data["id"] > 0

    def test_submit_thumbs_down_with_text(self, client, auth_headers):
        """测试提交 👎 + 文字反馈"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "openclaw",
                "conversation_id": 2,
                "message_id": 20,
                "rating": 1,
                "feedback_text": "回答不准确",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 1
        assert data["feedback_text"] == "回答不准确"

    def test_update_existing_feedback(self, client, auth_headers):
        """测试更新已有反馈（先 👎 后改 👍）"""
        payload = {
            "conversation_type": "chat",
            "conversation_id": 1,
            "message_id": 100,
            "rating": 1,
        }
        client.post("/api/v1/feedback", json=payload, headers=auth_headers)

        payload["rating"] = 5
        response = client.post("/api/v1/feedback", json=payload, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["rating"] == 5

    def test_invalid_rating(self, client, auth_headers):
        """测试无效评分被拒绝"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "chat",
                "conversation_id": 1,
                "message_id": 1,
                "rating": 10,
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_unauthorized(self, client):
        """测试未登录被拒绝"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "chat",
                "conversation_id": 1,
                "message_id": 1,
                "rating": 5,
            },
        )
        assert response.status_code == 401

    def test_skill_performance_admin_only(self, client, auth_headers, admin_headers):
        """测试 Skill 性能查询仅管理员可用"""
        response = client.get("/api/v1/feedback/skills", headers=auth_headers)
        assert response.status_code == 403

        response = client.get("/api/v1/feedback/skills", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_optimization_logs_admin_only(self, client, auth_headers, admin_headers):
        """测试优化日志仅管理员可用"""
        response = client.get("/api/v1/feedback/optimization-logs", headers=auth_headers)
        assert response.status_code == 403

        response = client.get("/api/v1/feedback/optimization-logs", headers=admin_headers)
        assert response.status_code == 200
