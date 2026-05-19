"""健康上下文 API 测试"""
import pytest
from datetime import date, timedelta
from app.models.user import User
from app.models.daily_health import GarminData, WaterIntake
from app.models.user_profile import UserProfile
from app.utils.timezone import get_china_today


@pytest.fixture
def test_user(db):
    user = User(
        username="contextuser",
        email="context@example.com",
        hashed_password="hashed_password",
        name="上下文测试用户",
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
def user_with_data(db, test_user):
    """用户 + Garmin 数据 + 用户画像"""
    # API 用 get_china_today() (Asia/Shanghai), 测试也得用同一个 today, 否则
    # CI 在 16:00-24:00 UTC 跨日时, date.today() 与 china_today 差一天 → 0ml.
    today = get_china_today()
    profile = UserProfile(
        user_id=test_user.id,
        height_cm=175,
        gender="male",
        birth_date=date(1990, 1, 1),
    )
    db.add(profile)

    # 添加 7 天 Garmin 数据
    for i in range(7):
        garmin = GarminData(
            user_id=test_user.id,
            record_date=today - timedelta(days=i),
            steps=8000 + i * 500 if i % 2 == 0 else 3000,
            active_minutes=40 if i % 2 == 0 else 10,
            deep_sleep_duration=80 + i * 2,
            hrv=45 if i == 0 else None,
            hrv_7day_avg=42 if i == 0 else None,
            body_battery_most_charged=70 if i == 0 else None,
            stress_level=35 if i == 0 else None,
        )
        db.add(garmin)

    # 今日饮水
    water = WaterIntake(
        user_id=test_user.id,
        record_date=today,
        amount=800,
        drink_type="水",
    )
    db.add(water)

    db.commit()
    return test_user


class TestHealthContextAPI:

    def test_cross_analysis_with_data(self, client, auth_headers, user_with_data):
        response = client.get(
            "/api/v1/health-context/me/cross-analysis",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should have at least recovery_readiness and hydration
        assert "recovery_readiness" in data or "hydration" in data

    def test_cross_analysis_recovery(self, client, auth_headers, user_with_data):
        response = client.get(
            "/api/v1/health-context/me/cross-analysis",
            headers=auth_headers,
        )
        data = response.json()
        if "recovery_readiness" in data:
            recovery = data["recovery_readiness"]
            assert "score" in recovery
            assert "grade" in recovery
            assert "suggestion" in recovery
            assert "factors" in recovery

    def test_cross_analysis_hydration(self, client, auth_headers, user_with_data):
        response = client.get(
            "/api/v1/health-context/me/cross-analysis",
            headers=auth_headers,
        )
        data = response.json()
        if "hydration" in data:
            h = data["hydration"]
            assert h["today_ml"] == 800
            assert h["remaining_ml"] > 0

    def test_cross_analysis_empty(self, client, auth_headers):
        """No data → empty result"""
        response = client.get(
            "/api/v1/health-context/me/cross-analysis",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # hydration always returns (even with 0ml)
        assert "hydration" in data

    def test_no_auth(self, client):
        response = client.get("/api/v1/health-context/me/cross-analysis")
        assert response.status_code in (401, 403)
