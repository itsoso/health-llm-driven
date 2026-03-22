"""NFC 碰触记录 API 测试"""
import pytest
from datetime import date, timedelta, time
from app.models.user import User


@pytest.fixture
def test_user(db):
    user = User(
        username="nfcuser",
        email="nfc@example.com",
        hashed_password="hashed_password",
        name="NFC测试用户",
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


@pytest.fixture(autouse=True)
def clear_timers():
    """清空大便计时器"""
    from app.api.nfc import _bowel_timers
    _bowel_timers.clear()
    yield
    _bowel_timers.clear()


class TestNfcWater:

    def test_record_water_default(self, client, auth_headers):
        """碰触记录默认 250ml 饮水"""
        response = client.post(
            "/api/v1/nfc/tap",
            json={"action": "water"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"
        assert "250ml" in data["message"]
        assert data["record_id"] is not None

    def test_record_water_custom_amount(self, client, auth_headers):
        """碰触记录自定义饮水量"""
        response = client.post(
            "/api/v1/nfc/tap",
            json={"action": "water", "amount_ml": 500, "drink_type": "茶"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "500ml" in response.json()["message"]
        assert "茶" in response.json()["message"]


class TestNfcBowel:

    def test_bowel_start_stop(self, client, auth_headers):
        """大便计时：开始 + 结束"""
        # 第一次碰触 → 开始计时
        r1 = client.post(
            "/api/v1/nfc/tap",
            json={"action": "bowel"},
            headers=auth_headers,
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "timer_started"
        assert "开始计时" in r1.json()["message"]

        # 查询计时状态
        status = client.get("/api/v1/nfc/bowel-status", headers=auth_headers)
        assert status.json()["timing"] is True

        # 第二次碰触 → 结束
        r2 = client.post(
            "/api/v1/nfc/tap",
            json={"action": "bowel"},
            headers=auth_headers,
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "timer_stopped"
        assert r2.json()["record_id"] is not None
        assert r2.json()["duration_minutes"] is not None

        # 计时器已清空
        status2 = client.get("/api/v1/nfc/bowel-status", headers=auth_headers)
        assert status2.json()["timing"] is False

    def test_bowel_no_active_timer(self, client, auth_headers):
        """无活跃计时器时查询"""
        status = client.get("/api/v1/nfc/bowel-status", headers=auth_headers)
        assert status.json()["timing"] is False


class TestNfcUrine:

    def test_record_urine(self, client, auth_headers):
        """碰触记录小便"""
        response = client.post(
            "/api/v1/nfc/tap",
            json={"action": "urine"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"
        assert data["record_id"] is not None


class TestNfcValidation:

    def test_invalid_action(self, client, auth_headers):
        """无效动作被拒绝"""
        response = client.post(
            "/api/v1/nfc/tap",
            json={"action": "invalid"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_unauthorized(self, client):
        """未登录被拒绝"""
        response = client.post(
            "/api/v1/nfc/tap",
            json={"action": "water"},
        )
        assert response.status_code == 401


class TestExcretionPatterns:

    def test_patterns_empty(self, client, auth_headers):
        """无数据时返回空分析"""
        response = client.get("/api/v1/excretion/patterns/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["bowel"]["total_count"] == 0
        assert data["urine"]["total_count"] == 0

    def test_patterns_with_data(self, client, auth_headers, db, test_user):
        """有数据时正确分析"""
        from app.models.excretion import ExcretionRecord

        today = date.today()
        # 添加 7 天数据：每天早上 8 点大便 + 6 次小便
        for i in range(7):
            d = today - timedelta(days=i)
            db.add(ExcretionRecord(
                user_id=test_user.id,
                record_date=d,
                record_time=time(8, 30),
                type="bowel",
                duration_minutes=7,
            ))
            for h in [7, 10, 13, 16, 19, 22]:
                db.add(ExcretionRecord(
                    user_id=test_user.id,
                    record_date=d,
                    record_time=time(h, 0),
                    type="urine",
                ))
        db.commit()

        response = client.get("/api/v1/excretion/patterns/me?days=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # 大便分析
        assert data["bowel"]["total_count"] == 7
        assert data["bowel"]["avg_frequency_per_day"] == 1.0
        assert "早晨" in data["bowel"]["most_common_period"]
        assert data["bowel"]["avg_duration_minutes"] == 7.0
        assert data["bowel"]["regularity_score"] >= 60  # 规律

        # 小便分析
        assert data["urine"]["total_count"] == 42
        assert data["urine"]["avg_frequency_per_day"] == 6.0
        assert data["urine"]["nighttime_avg"] >= 0

        # 应有洞察
        assert len(data["insights"]) > 0
