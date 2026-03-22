"""NFC 碰触记录 API 测试"""
import pytest
from datetime import date, timedelta, time, datetime, timezone
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
def admin_user(db):
    user = User(
        username="nfcadmin",
        email="nfcadmin@example.com",
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
def child_user(db):
    user = User(
        username="child",
        email="child@example.com",
        hashed_password="hashed_password",
        name="小明",
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


@pytest.fixture
def admin_headers(client, admin_user):
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clear_state(db):
    """清空防抖缓存和计时器"""
    from app.api.nfc import _last_tap, BowelTimer
    _last_tap.clear()
    db.query(BowelTimer).delete()
    db.commit()
    yield
    _last_tap.clear()


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

    def test_water_debounce(self, client, auth_headers):
        """快速双击饮水被去重"""
        r1 = client.post("/api/v1/nfc/tap", json={"action": "water"}, headers=auth_headers)
        assert r1.json()["status"] == "recorded"

        r2 = client.post("/api/v1/nfc/tap", json={"action": "water"}, headers=auth_headers)
        assert r2.json()["status"] == "debounced"


class TestNfcBowel:

    def test_bowel_start_stop(self, client, auth_headers):
        """大便计时：开始 + 结束"""
        r1 = client.post("/api/v1/nfc/tap", json={"action": "bowel"}, headers=auth_headers)
        assert r1.status_code == 200
        assert r1.json()["status"] == "timer_started"

        status = client.get("/api/v1/nfc/bowel-status", headers=auth_headers)
        assert status.json()["timing"] is True

        r2 = client.post("/api/v1/nfc/tap", json={"action": "bowel"}, headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "timer_stopped"
        assert r2.json()["record_id"] is not None

        status2 = client.get("/api/v1/nfc/bowel-status", headers=auth_headers)
        assert status2.json()["timing"] is False

    def test_bowel_no_active_timer(self, client, auth_headers):
        """无活跃计时器时查询"""
        status = client.get("/api/v1/nfc/bowel-status", headers=auth_headers)
        assert status.json()["timing"] is False

    def test_bowel_timer_persisted(self, client, auth_headers, db):
        """计时器持久化到 DB，模拟重启不丢失"""
        from app.api.nfc import BowelTimer

        # 开始计时
        client.post("/api/v1/nfc/tap", json={"action": "bowel"}, headers=auth_headers)

        # 验证 DB 中有记录
        timer = db.query(BowelTimer).first()
        assert timer is not None
        assert timer.start_time is not None


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


class TestNfcOnBehalfOf:

    def test_admin_record_for_child(self, client, admin_headers, child_user):
        """管理员为孩子代记"""
        response = client.post(
            "/api/v1/nfc/tap",
            json={"action": "water", "on_behalf_of": child_user.id},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "小明" in response.json()["message"]

    def test_non_admin_rejected(self, client, auth_headers, child_user):
        """非管理员代记被拒绝"""
        response = client.post(
            "/api/v1/nfc/tap",
            json={"action": "water", "on_behalf_of": child_user.id},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_nonexistent_user_rejected(self, client, admin_headers):
        """代记不存在的用户返回 404"""
        response = client.post(
            "/api/v1/nfc/tap",
            json={"action": "water", "on_behalf_of": 99999},
            headers=admin_headers,
        )
        assert response.status_code == 404


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

        assert data["bowel"]["total_count"] == 7
        assert data["bowel"]["avg_frequency_per_day"] == 1.0
        assert "早晨" in data["bowel"]["most_common_period"]
        assert data["bowel"]["avg_duration_minutes"] == 7.0
        assert data["bowel"]["regularity_score"] >= 60

        assert data["urine"]["total_count"] == 42
        assert data["urine"]["avg_frequency_per_day"] == 6.0
        # 夜尿：每天 22:00 各一次 = 7 次 / 7 天 = 1.0
        assert data["urine"]["nighttime_avg"] == 1.0

        assert len(data["insights"]) > 0
