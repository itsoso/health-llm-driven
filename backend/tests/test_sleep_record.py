"""睡眠记录API测试"""
import pytest
from datetime import date, datetime, timedelta
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="sleepuser",
        email="sleep@example.com",
        hashed_password="hashed_password",
        name="睡眠测试用户",
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
def sample_sleep_data():
    """示例睡眠记录"""
    today = date.today()
    yesterday = today - timedelta(days=1)
    return {
        "record_date": str(today),
        "bedtime": f"{yesterday}T23:00:00",
        "wake_time": f"{today}T07:00:00",
        "sleep_quality": 4,
        "wake_count": 1,
        "had_dream": True,
        "dream_description": "梦到了大海",
        "fall_asleep_difficulty": 2,
        "morning_feeling": 4,
        "notes": "睡得不错"
    }


@pytest.fixture
def sample_sleep_data_poor():
    """示例差质量睡眠"""
    today = date.today()
    yesterday = today - timedelta(days=1)
    return {
        "record_date": str(today),
        "bedtime": f"{yesterday}T01:30:00",
        "wake_time": f"{today}T06:00:00",
        "sleep_quality": 2,
        "wake_count": 3,
        "had_dream": False,
        "fall_asleep_difficulty": 4,
        "morning_feeling": 2,
    }


class TestSleepCRUD:
    """睡眠记录CRUD测试"""

    def test_create_sleep_record(self, client, auth_headers, sample_sleep_data):
        """测试创建睡眠记录"""
        response = client.post(
            "/api/v1/sleep/records",
            json=sample_sleep_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sleep_quality"] == 4
        assert data["wake_count"] == 1
        assert data["had_dream"] is True
        assert data["dream_description"] == "梦到了大海"
        assert data["total_duration_minutes"] == 480  # 8 hours
        assert "id" in data

    def test_create_minimal_sleep_record(self, client, auth_headers):
        """测试创建最小睡眠记录"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        minimal = {
            "record_date": str(today),
            "bedtime": f"{yesterday}T23:00:00",
            "wake_time": f"{today}T06:00:00",
            "sleep_quality": 3,
        }
        response = client.post(
            "/api/v1/sleep/records",
            json=minimal,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sleep_quality"] == 3
        assert data["total_duration_minutes"] == 420  # 7 hours

    def test_create_sleep_record_duration_calculation(self, client, auth_headers):
        """测试睡眠时长自动计算"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        data = {
            "record_date": str(today),
            "bedtime": f"{yesterday}T22:30:00",
            "wake_time": f"{today}T06:45:00",
            "sleep_quality": 4,
        }
        response = client.post("/api/v1/sleep/records", json=data, headers=auth_headers)
        assert response.status_code == 200
        result = response.json()
        # 22:30 -> 06:45 = 8h15m = 495 minutes
        assert result["total_duration_minutes"] == 495

    def test_get_my_records(self, client, auth_headers, sample_sleep_data):
        """测试获取记录列表"""
        client.post("/api/v1/sleep/records", json=sample_sleep_data, headers=auth_headers)

        response = client.get("/api/v1/sleep/records/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_today_record(self, client, auth_headers, sample_sleep_data):
        """测试获取今日记录"""
        client.post("/api/v1/sleep/records", json=sample_sleep_data, headers=auth_headers)

        response = client.get("/api/v1/sleep/records/me/today", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data["sleep_quality"] == 4

    def test_get_today_record_empty(self, client, auth_headers):
        """测试今日无记录"""
        response = client.get("/api/v1/sleep/records/me/today", headers=auth_headers)
        assert response.status_code == 200
        # null 或空

    def test_get_single_record(self, client, auth_headers, sample_sleep_data):
        """测试获取单条记录"""
        create_resp = client.post("/api/v1/sleep/records", json=sample_sleep_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/sleep/records/{record_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == record_id

    def test_get_nonexistent_record(self, client, auth_headers):
        """测试获取不存在的记录"""
        response = client.get("/api/v1/sleep/records/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_update_record(self, client, auth_headers, sample_sleep_data):
        """测试更新记录"""
        create_resp = client.post("/api/v1/sleep/records", json=sample_sleep_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        update_data = {
            "sleep_quality": 5,
            "notes": "更新：其实睡得很好",
        }
        response = client.put(
            f"/api/v1/sleep/records/{record_id}",
            json=update_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sleep_quality"] == 5
        assert data["notes"] == "更新：其实睡得很好"

    def test_update_recalculates_duration(self, client, auth_headers, sample_sleep_data):
        """测试更新时间会重新计算时长"""
        create_resp = client.post("/api/v1/sleep/records", json=sample_sleep_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        today = date.today()
        update_data = {
            "wake_time": f"{today}T09:00:00",
        }
        response = client.put(
            f"/api/v1/sleep/records/{record_id}",
            json=update_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # 原来 23:00->07:00=480min, 改 wake_time 到 09:00 => 23:00->09:00=600min
        assert data["total_duration_minutes"] == 600

    def test_update_nonexistent_record(self, client, auth_headers):
        """测试更新不存在的记录"""
        response = client.put(
            "/api/v1/sleep/records/99999",
            json={"sleep_quality": 3},
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_delete_record(self, client, auth_headers, sample_sleep_data):
        """测试删除记录"""
        create_resp = client.post("/api/v1/sleep/records", json=sample_sleep_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        response = client.delete(f"/api/v1/sleep/records/{record_id}", headers=auth_headers)
        assert response.status_code == 200

        # 确认已删除
        get_resp = client.get(f"/api/v1/sleep/records/{record_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_delete_nonexistent_record(self, client, auth_headers):
        """测试删除不存在的记录"""
        response = client.delete("/api/v1/sleep/records/99999", headers=auth_headers)
        assert response.status_code == 404


class TestSleepValidation:
    """睡眠记录验证测试"""

    def test_invalid_sleep_quality(self, client, auth_headers):
        """测试无效的睡眠质量值"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        data = {
            "record_date": str(today),
            "bedtime": f"{yesterday}T23:00:00",
            "wake_time": f"{today}T07:00:00",
            "sleep_quality": 6,  # 超出 1-5 范围
        }
        response = client.post("/api/v1/sleep/records", json=data, headers=auth_headers)
        assert response.status_code == 422

    def test_invalid_sleep_quality_zero(self, client, auth_headers):
        """测试睡眠质量为0"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        data = {
            "record_date": str(today),
            "bedtime": f"{yesterday}T23:00:00",
            "wake_time": f"{today}T07:00:00",
            "sleep_quality": 0,
        }
        response = client.post("/api/v1/sleep/records", json=data, headers=auth_headers)
        assert response.status_code == 422

    def test_wake_time_before_bedtime(self, client, auth_headers):
        """测试醒来时间早于入睡时间"""
        today = date.today()
        data = {
            "record_date": str(today),
            "bedtime": f"{today}T07:00:00",
            "wake_time": f"{today}T06:00:00",  # 比 bedtime 早
            "sleep_quality": 3,
        }
        response = client.post("/api/v1/sleep/records", json=data, headers=auth_headers)
        assert response.status_code == 422

    def test_fall_asleep_difficulty_range(self, client, auth_headers):
        """测试入睡难度范围 (1-5)"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        # 有效值
        data = {
            "record_date": str(today),
            "bedtime": f"{yesterday}T23:00:00",
            "wake_time": f"{today}T07:00:00",
            "sleep_quality": 3,
            "fall_asleep_difficulty": 3,
        }
        resp = client.post("/api/v1/sleep/records", json=data, headers=auth_headers)
        assert resp.status_code == 200

        # 无效值
        data["fall_asleep_difficulty"] = 6
        resp = client.post("/api/v1/sleep/records", json=data, headers=auth_headers)
        assert resp.status_code == 422

    def test_morning_feeling_range(self, client, auth_headers):
        """测试醒后感觉范围 (1-5)"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        data = {
            "record_date": str(today),
            "bedtime": f"{yesterday}T23:00:00",
            "wake_time": f"{today}T07:00:00",
            "sleep_quality": 3,
            "morning_feeling": 6,
        }
        resp = client.post("/api/v1/sleep/records", json=data, headers=auth_headers)
        assert resp.status_code == 422


class TestSleepStats:
    """睡眠统计测试"""

    def test_get_stats_empty(self, client, auth_headers):
        """测试空数据统计"""
        response = client.get("/api/v1/sleep/stats/me?days=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] == 0

    def test_get_stats_with_data(self, client, auth_headers, sample_sleep_data):
        """测试有数据的统计"""
        client.post("/api/v1/sleep/records", json=sample_sleep_data, headers=auth_headers)

        response = client.get("/api/v1/sleep/stats/me?days=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] == 1
        assert data["avg_sleep_quality"] == 4.0
        assert data["avg_duration_hours"] == 8.0
        assert data["avg_wake_count"] == 1.0
        assert len(data["daily_trend"]) == 1

    def test_stats_quality_distribution(self, client, auth_headers):
        """测试睡眠质量分布"""
        today = date.today()
        for i, quality in enumerate([3, 4, 4, 5]):
            d = today - timedelta(days=i)
            prev = d - timedelta(days=1)
            data = {
                "record_date": str(d),
                "bedtime": f"{prev}T23:00:00",
                "wake_time": f"{d}T07:00:00",
                "sleep_quality": quality,
            }
            client.post("/api/v1/sleep/records", json=data, headers=auth_headers)

        response = client.get("/api/v1/sleep/stats/me?days=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        dist = data["quality_distribution"]
        assert dist.get("4", dist.get(4, 0)) == 2
        assert dist.get("3", dist.get(3, 0)) == 1
        assert dist.get("5", dist.get(5, 0)) == 1

    def test_stats_dream_frequency(self, client, auth_headers):
        """测试做梦频率"""
        today = date.today()
        for i, dream in enumerate([True, False, True]):
            d = today - timedelta(days=i)
            prev = d - timedelta(days=1)
            data = {
                "record_date": str(d),
                "bedtime": f"{prev}T23:00:00",
                "wake_time": f"{d}T07:00:00",
                "sleep_quality": 3,
                "had_dream": dream,
            }
            client.post("/api/v1/sleep/records", json=data, headers=auth_headers)

        response = client.get("/api/v1/sleep/stats/me?days=7", headers=auth_headers)
        data = response.json()
        # 3条记录中2条做梦 = 66.7%
        assert data["dream_frequency"] == 66.7

    def test_stats_avg_times(self, client, auth_headers):
        """测试平均入睡/醒来时间"""
        today = date.today()
        for i in range(2):
            d = today - timedelta(days=i)
            prev = d - timedelta(days=1)
            data = {
                "record_date": str(d),
                "bedtime": f"{prev}T23:00:00",
                "wake_time": f"{d}T07:00:00",
                "sleep_quality": 4,
            }
            client.post("/api/v1/sleep/records", json=data, headers=auth_headers)

        response = client.get("/api/v1/sleep/stats/me?days=7", headers=auth_headers)
        data = response.json()
        assert data["avg_bedtime"] == "23:00"
        assert data["avg_wake_time"] == "07:00"


class TestSleepAuth:
    """睡眠记录权限测试"""

    def test_unauthorized_create(self, client, sample_sleep_data):
        """测试未授权创建"""
        response = client.post("/api/v1/sleep/records", json=sample_sleep_data)
        assert response.status_code == 401

    def test_unauthorized_list(self, client):
        """测试未授权列表"""
        response = client.get("/api/v1/sleep/records/me")
        assert response.status_code == 401

    def test_unauthorized_stats(self, client):
        """测试未授权统计"""
        response = client.get("/api/v1/sleep/stats/me")
        assert response.status_code == 401

    def test_cannot_access_other_user_record(self, client, db, auth_headers, sample_sleep_data):
        """测试不能访问其他用户的记录"""
        create_resp = client.post("/api/v1/sleep/records", json=sample_sleep_data, headers=auth_headers)
        record_id = create_resp.json()["id"]

        other_user = User(
            username="otheruser2",
            email="other2@example.com",
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

        response = client.get(f"/api/v1/sleep/records/{record_id}", headers=other_headers)
        assert response.status_code == 404
