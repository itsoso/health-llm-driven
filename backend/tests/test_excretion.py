"""排泄记录API测试"""
import pytest
from datetime import date, time
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="excretionuser",
        email="excretion@example.com",
        hashed_password="hashed_password",
        name="排泄测试用户",
        is_active=True,
        is_approved=True,
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
def sample_bowel_data():
    """示例大便记录"""
    return {
        "record_date": str(date.today()),
        "record_time": "08:30:00",
        "type": "bowel",
        "stool_type": 4,
        "color": "brown",
        "amount": "medium",
        "duration_minutes": 5,
        "blood_present": False,
        "urgency": 2,
        "pain_level": 0,
        "notes": "正常排便"
    }


@pytest.fixture
def sample_urine_data():
    """示例小便记录"""
    return {
        "record_date": str(date.today()),
        "record_time": "09:15:00",
        "type": "urine",
        "urine_color": "light_yellow",
        "urine_amount": "medium",
        "urgency": 1,
        "pain_level": 0,
    }


class TestExcretionCRUD:
    """排泄记录CRUD测试"""

    def test_create_bowel_record(self, client, auth_headers, sample_bowel_data):
        """测试创建大便记录"""
        response = client.post(
            "/api/v1/excretion/records",
            json=sample_bowel_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "bowel"
        assert data["stool_type"] == 4
        assert data["color"] == "brown"
        assert data["amount"] == "medium"
        assert data["blood_present"] is False
        assert "id" in data

    def test_create_urine_record(self, client, auth_headers, sample_urine_data):
        """测试创建小便记录"""
        response = client.post(
            "/api/v1/excretion/records",
            json=sample_urine_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "urine"
        assert data["urine_color"] == "light_yellow"
        assert data["urine_amount"] == "medium"
        assert "id" in data

    def test_create_minimal_bowel_record(self, client, auth_headers):
        """测试创建最小大便记录（仅必填字段）"""
        minimal = {
            "record_date": str(date.today()),
            "type": "bowel",
        }
        response = client.post(
            "/api/v1/excretion/records",
            json=minimal,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "bowel"
        assert data["stool_type"] is None

    def test_create_minimal_urine_record(self, client, auth_headers):
        """测试创建最小小便记录"""
        minimal = {
            "record_date": str(date.today()),
            "type": "urine",
        }
        response = client.post(
            "/api/v1/excretion/records",
            json=minimal,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "urine"

    def test_get_my_records(self, client, auth_headers, sample_bowel_data, sample_urine_data):
        """测试获取记录列表"""
        client.post("/api/v1/excretion/records", json=sample_bowel_data, headers=auth_headers)
        client.post("/api/v1/excretion/records", json=sample_urine_data, headers=auth_headers)

        response = client.get("/api/v1/excretion/records/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_get_my_records_filter_type(self, client, auth_headers, sample_bowel_data, sample_urine_data):
        """测试按类型筛选记录"""
        client.post("/api/v1/excretion/records", json=sample_bowel_data, headers=auth_headers)
        client.post("/api/v1/excretion/records", json=sample_urine_data, headers=auth_headers)

        response = client.get("/api/v1/excretion/records/me?type=bowel", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(r["type"] == "bowel" for r in data)

        response = client.get("/api/v1/excretion/records/me?type=urine", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert all(r["type"] == "urine" for r in data)

    def test_get_today_records(self, client, auth_headers, sample_bowel_data):
        """测试获取今日记录"""
        client.post("/api/v1/excretion/records", json=sample_bowel_data, headers=auth_headers)

        response = client.get("/api/v1/excretion/records/me/today", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_single_record(self, client, auth_headers, sample_bowel_data):
        """测试获取单条记录"""
        create_resp = client.post("/api/v1/excretion/records", json=sample_bowel_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/excretion/records/{record_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == record_id
        assert data["type"] == "bowel"

    def test_get_nonexistent_record(self, client, auth_headers):
        """测试获取不存在的记录"""
        response = client.get("/api/v1/excretion/records/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_update_record(self, client, auth_headers, sample_bowel_data):
        """测试更新记录"""
        create_resp = client.post("/api/v1/excretion/records", json=sample_bowel_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        update_data = {
            "stool_type": 3,
            "color": "green",
            "notes": "更新备注",
        }
        response = client.put(f"/api/v1/excretion/records/{record_id}", json=update_data, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["stool_type"] == 3
        assert data["color"] == "green"
        assert data["notes"] == "更新备注"

    def test_update_nonexistent_record(self, client, auth_headers):
        """测试更新不存在的记录"""
        response = client.put(
            "/api/v1/excretion/records/99999",
            json={"notes": "test"},
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_delete_record(self, client, auth_headers, sample_bowel_data):
        """测试删除记录"""
        create_resp = client.post("/api/v1/excretion/records", json=sample_bowel_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        response = client.delete(f"/api/v1/excretion/records/{record_id}", headers=auth_headers)
        assert response.status_code == 200

        # 确认已删除
        get_resp = client.get(f"/api/v1/excretion/records/{record_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_delete_nonexistent_record(self, client, auth_headers):
        """测试删除不存在的记录"""
        response = client.delete("/api/v1/excretion/records/99999", headers=auth_headers)
        assert response.status_code == 404


class TestExcretionValidation:
    """排泄记录验证测试"""

    def test_invalid_type(self, client, auth_headers):
        """测试无效的类型"""
        data = {
            "record_date": str(date.today()),
            "type": "invalid",
        }
        response = client.post("/api/v1/excretion/records", json=data, headers=auth_headers)
        assert response.status_code == 422

    def test_stool_type_range(self, client, auth_headers):
        """测试Bristol量表范围 (1-7)"""
        # 有效值
        for st in [1, 4, 7]:
            data = {"record_date": str(date.today()), "type": "bowel", "stool_type": st}
            resp = client.post("/api/v1/excretion/records", json=data, headers=auth_headers)
            assert resp.status_code == 200, f"Bristol {st} 应该有效"

        # 无效值
        for st in [0, 8]:
            data = {"record_date": str(date.today()), "type": "bowel", "stool_type": st}
            resp = client.post("/api/v1/excretion/records", json=data, headers=auth_headers)
            assert resp.status_code == 422, f"Bristol {st} 应该无效"

    def test_urgency_range(self, client, auth_headers):
        """测试紧迫感范围 (1-5)"""
        # 有效值
        data = {"record_date": str(date.today()), "type": "bowel", "urgency": 3}
        resp = client.post("/api/v1/excretion/records", json=data, headers=auth_headers)
        assert resp.status_code == 200

        # 无效值
        data = {"record_date": str(date.today()), "type": "bowel", "urgency": 6}
        resp = client.post("/api/v1/excretion/records", json=data, headers=auth_headers)
        assert resp.status_code == 422

    def test_pain_level_range(self, client, auth_headers):
        """测试疼痛等级范围 (0-5)"""
        # 有效值
        data = {"record_date": str(date.today()), "type": "bowel", "pain_level": 0}
        resp = client.post("/api/v1/excretion/records", json=data, headers=auth_headers)
        assert resp.status_code == 200

        data = {"record_date": str(date.today()), "type": "bowel", "pain_level": 5}
        resp = client.post("/api/v1/excretion/records", json=data, headers=auth_headers)
        assert resp.status_code == 200

        # 无效值
        data = {"record_date": str(date.today()), "type": "bowel", "pain_level": 6}
        resp = client.post("/api/v1/excretion/records", json=data, headers=auth_headers)
        assert resp.status_code == 422


class TestExcretionStats:
    """排泄统计测试"""

    def test_get_stats_empty(self, client, auth_headers):
        """测试空数据统计"""
        response = client.get("/api/v1/excretion/stats/me?days=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] == 0
        assert data["bowel_count"] == 0
        assert data["urine_count"] == 0

    def test_get_stats_with_data(self, client, auth_headers, sample_bowel_data, sample_urine_data):
        """测试有数据的统计"""
        client.post("/api/v1/excretion/records", json=sample_bowel_data, headers=auth_headers)
        client.post("/api/v1/excretion/records", json=sample_urine_data, headers=auth_headers)

        response = client.get("/api/v1/excretion/stats/me?days=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] == 2
        assert data["bowel_count"] == 1
        assert data["urine_count"] == 1
        assert data["avg_stool_type"] == 4.0
        assert data["blood_count"] == 0
        assert len(data["daily_summary"]) >= 1

    def test_stats_bristol_distribution(self, client, auth_headers):
        """测试Bristol分布统计"""
        for st in [3, 4, 4, 5]:
            data = {"record_date": str(date.today()), "type": "bowel", "stool_type": st}
            client.post("/api/v1/excretion/records", json=data, headers=auth_headers)

        response = client.get("/api/v1/excretion/stats/me?days=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        dist = data["stool_type_distribution"]
        assert dist.get("4", dist.get(4, 0)) == 2
        assert dist.get("3", dist.get(3, 0)) == 1
        assert dist.get("5", dist.get(5, 0)) == 1

    def test_stats_blood_count(self, client, auth_headers):
        """测试便血统计"""
        # 一条有血，一条无血
        client.post("/api/v1/excretion/records", json={
            "record_date": str(date.today()), "type": "bowel", "blood_present": True
        }, headers=auth_headers)
        client.post("/api/v1/excretion/records", json={
            "record_date": str(date.today()), "type": "bowel", "blood_present": False
        }, headers=auth_headers)

        response = client.get("/api/v1/excretion/stats/me?days=7", headers=auth_headers)
        data = response.json()
        assert data["blood_count"] == 1


class TestExcretionAuth:
    """排泄记录权限测试"""

    def test_unauthorized_create(self, client, sample_bowel_data):
        """测试未授权创建"""
        response = client.post("/api/v1/excretion/records", json=sample_bowel_data)
        assert response.status_code == 401

    def test_unauthorized_list(self, client):
        """测试未授权列表"""
        response = client.get("/api/v1/excretion/records/me")
        assert response.status_code == 401

    def test_unauthorized_stats(self, client):
        """测试未授权统计"""
        response = client.get("/api/v1/excretion/stats/me")
        assert response.status_code == 401

    def test_cannot_access_other_user_record(self, client, db, auth_headers, sample_bowel_data):
        """测试不能访问其他用户的记录"""
        # 用当前用户创建记录
        create_resp = client.post("/api/v1/excretion/records", json=sample_bowel_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        # 创建另一个用户
        other_user = User(
            username="otheruser",
            email="other@example.com",
            hashed_password="hashed_password",
            name="其他用户",
            is_active=True,
            is_approved=True,
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)

        from app.services.auth import auth_service
        other_token = auth_service.create_access_token({"sub": str(other_user.id)})
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # 另一个用户不应能获取该记录
        response = client.get(f"/api/v1/excretion/records/{record_id}", headers=other_headers)
        assert response.status_code == 404
