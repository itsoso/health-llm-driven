"""通用症状记录API测试"""
import pytest
from datetime import date, datetime, timedelta
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="symptomuser",
        email="symptom@example.com",
        hashed_password="hashed_password",
        name="症状测试用户",
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    """获取认证 headers"""
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def second_user(db):
    """创建第二个测试用户（权限测试用）"""
    user = User(
        username="symptomuser2",
        email="symptom2@example.com",
        hashed_password="hashed_password",
        name="症状测试用户2",
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestSymptomsAPI:
    """症状记录API测试类"""

    def test_create_symptom(self, client, auth_headers, test_user):
        """测试创建症状记录"""
        payload = {
            "body_part": "eye",
            "description": "眼睛痒",
            "severity": 3,
            "triggers": ["pollen"],
        }
        response = client.post(
            "/api/v1/symptoms",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["body_part"] == "eye"
        assert data["description"] == "眼睛痒"
        assert data["severity"] == 3
        assert data["triggers"] == ["pollen"]
        assert "id" in data
        assert data["user_id"] == test_user.id

    def test_create_symptom_minimal(self, client, auth_headers):
        """测试创建最小症状记录"""
        minimal_data = {
            "body_part": "respiratory",
            "description": "嗓子有痰",
        }
        response = client.post(
            "/api/v1/symptoms",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["body_part"] == "respiratory"
        assert data["description"] == "嗓子有痰"
        assert data["severity"] is None

    def test_invalid_body_part(self, client, auth_headers):
        """测试无效的 body_part"""
        payload = {
            "body_part": "invalid_part",
            "description": "测试",
        }
        response = client.post(
            "/api/v1/symptoms",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "body_part" in response.json()["detail"]

    def test_create_all_valid_body_parts(self, client, auth_headers):
        """测试所有有效的 body_part"""
        valid_parts = ["eye", "respiratory", "skin", "digestive",
                       "musculoskeletal", "head", "general", "other"]
        for part in valid_parts:
            payload = {
                "body_part": part,
                "description": f"测试 {part}",
            }
            response = client.post(
                "/api/v1/symptoms",
                json=payload,
                headers=auth_headers
            )
            assert response.status_code == 201, f"body_part {part} 创建失败"

    def test_get_my_symptoms_default_range(self, client, auth_headers):
        """测试获取我的症状记录（默认30天）"""
        # 创建记录
        payload = {
            "body_part": "eye",
            "description": "眼睛痒",
        }
        client.post("/api/v1/symptoms", json=payload, headers=auth_headers)

        # 获取记录
        response = client.get(
            "/api/v1/symptoms/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_symptoms_with_date_filter(self, client, auth_headers):
        """测试带日期过滤的症状列表"""
        # 创建记录
        payload = {
            "body_part": "skin",
            "description": "皮肤起疹",
            "occurred_at": (datetime.utcnow() - timedelta(days=15)).isoformat(),
        }
        client.post("/api/v1/symptoms", json=payload, headers=auth_headers)

        # 创建另一条记录（今天）
        payload2 = {
            "body_part": "eye",
            "description": "眼睛痒",
        }
        client.post("/api/v1/symptoms", json=payload2, headers=auth_headers)

        # 查询最近7天
        start_date = (date.today() - timedelta(days=7)).isoformat()
        response = client.get(
            f"/api/v1/symptoms/me?start_date={start_date}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # 应该只有今天那条
        assert len(data) == 1
        assert data[0]["body_part"] == "eye"

    def test_get_symptoms_body_part_filter(self, client, auth_headers):
        """测试按身体部位过滤"""
        # 创建不同部位的症状
        client.post("/api/v1/symptoms", json={"body_part": "eye", "description": "眼"}, headers=auth_headers)
        client.post("/api/v1/symptoms", json={"body_part": "respiratory", "description": "嗓子"}, headers=auth_headers)
        client.post("/api/v1/symptoms", json={"body_part": "eye", "description": "眼睛红"}, headers=auth_headers)

        # 只查眼部症状
        response = client.get(
            "/api/v1/symptoms/me?body_part=eye",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(d["body_part"] == "eye" for d in data)

    def test_delete_symptom(self, client, auth_headers):
        """测试删除症状记录"""
        # 创建记录
        create_response = client.post(
            "/api/v1/symptoms",
            json={"body_part": "eye", "description": "眼睛痒"},
            headers=auth_headers
        )
        record_id = create_response.json()["id"]

        # 删除记录
        delete_response = client.delete(
            f"/api/v1/symptoms/{record_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 204

        # 确认已删除
        get_response = client.get(
            "/api/v1/symptoms/me",
            headers=auth_headers
        )
        data = get_response.json()
        assert len(data) == 0

    def test_delete_other_user_symptom_403(self, client, test_user, second_user):
        """测试删除其他用户的症状记录（403）"""
        # 创建第二个用户的认证
        from app.services.auth import auth_service
        token2 = auth_service.create_access_token({"sub": str(second_user.id)})
        headers2 = {"Authorization": f"Bearer {token2}"}

        # 用户2创建记录
        create_response = client.post(
            "/api/v1/symptoms",
            json={"body_part": "eye", "description": "用户2眼睛痒"},
            headers=headers2
        )
        record_id = create_response.json()["id"]

        # 用户1尝试删除用户2的记录
        token1 = auth_service.create_access_token({"sub": str(test_user.id)})
        headers1 = {"Authorization": f"Bearer {token1}"}
        delete_response = client.delete(
            f"/api/v1/symptoms/{record_id}",
            headers=headers1
        )
        assert delete_response.status_code == 403

    def test_delete_nonexistent_symptom_404(self, client, auth_headers):
        """测试删除不存在的症状记录（404）"""
        response = client.delete(
            "/api/v1/symptoms/99999",
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_unauthorized_access(self, client):
        """测试未授权访问"""
        response = client.post("/api/v1/symptoms", json={"body_part": "eye", "description": "测试"})
        assert response.status_code == 401


class TestSymptomValidation:
    """症状记录验证测试"""

    def test_severity_range_1_to_10(self, client, auth_headers):
        """测试严重度 1-10 范围"""
        for severity in [1, 5, 10]:
            payload = {
                "body_part": "eye",
                "description": "测试",
                "severity": severity,
            }
            response = client.post("/api/v1/symptoms", json=payload, headers=auth_headers)
            assert response.status_code == 201, f"severity {severity} 应该允许"

    def test_severity_out_of_range(self, client, auth_headers):
        """测试严重度超出范围"""
        payload = {
            "body_part": "eye",
            "description": "测试",
            "severity": 11,
        }
        response = client.post("/api/v1/symptoms", json=payload, headers=auth_headers)
        assert response.status_code == 422

    def test_negative_severity_rejected(self, client, auth_headers):
        """测试负严重度被拒绝"""
        payload = {
            "body_part": "eye",
            "description": "测试",
            "severity": -1,
        }
        response = client.post("/api/v1/symptoms", json=payload, headers=auth_headers)
        assert response.status_code == 422

    def test_duration_minutes_positive(self, client, auth_headers):
        """测试持续时间为正数"""
        payload = {
            "body_part": "head",
            "description": "头痛",
            "duration_minutes": 30,
        }
        response = client.post("/api/v1/symptoms", json=payload, headers=auth_headers)
        assert response.status_code == 201

    def test_negative_duration_minutes_rejected(self, client, auth_headers):
        """测试负持续时间被拒绝"""
        payload = {
            "body_part": "head",
            "description": "头痛",
            "duration_minutes": -10,
        }
        response = client.post("/api/v1/symptoms", json=payload, headers=auth_headers)
        assert response.status_code == 422

    def test_source_validation(self, client, auth_headers):
        """测试 source 枚举"""
        valid_sources = ["manual", "voice", "siri"]
        for source in valid_sources:
            payload = {
                "body_part": "eye",
                "description": "测试",
                "source": source,
            }
            response = client.post("/api/v1/symptoms", json=payload, headers=auth_headers)
            assert response.status_code == 201, f"source {source} 应该允许"

    def test_invalid_source_rejected(self, client, auth_headers):
        """测试无效 source 被拒绝"""
        payload = {
            "body_part": "eye",
            "description": "测试",
            "source": "invalid",
        }
        response = client.post("/api/v1/symptoms", json=payload, headers=auth_headers)
        assert response.status_code == 422
