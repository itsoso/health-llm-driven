"""健康评分体系测试 - TDD"""
import pytest
from datetime import date, timedelta, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.daily_health import GarminData, DietRecord
from app.models.weight import WeightRecord
from app.models.mood import MoodRecord
from app.services.health_score_service import HealthScoreService


@pytest.fixture
def hs_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def hs_user(hs_db):
    user = User(username="hs_test", email="hs@test.com", hashed_password="hash", name="评分测试", is_active=True, is_approved=True)
    hs_db.add(user)
    hs_db.commit()
    hs_db.refresh(user)
    return user


@pytest.fixture
def hs_service():
    return HealthScoreService()


@pytest.fixture
def sample_health_data(hs_db, hs_user):
    """创建7天完整健康数据"""
    today = date.today()
    for i in range(7):
        d = today - timedelta(days=6 - i)
        # Garmin 数据
        garmin = GarminData(
            user_id=hs_user.id,
            record_date=d,
            steps=8000 + i * 500,
            resting_heart_rate=62 - i,
            sleep_score=75 + i,
            total_sleep_duration=420 + i * 10,
            deep_sleep_duration=80 + i * 5,
            stress_level=35 - i,
            body_battery_most_charged=70 + i * 3,
            calories_burned=2000 + i * 100,
        )
        hs_db.add(garmin)

        # 饮食数据
        diet = DietRecord(
            user_id=hs_user.id,
            record_date=d,
            meal_type="lunch",
            food_items="测试食物",
            calories=600 + i * 20,
            protein=25 + i * 2,
            carbs=60 + i * 3,
            fat=20 + i,
        )
        hs_db.add(diet)

        # 情绪数据
        mood = MoodRecord(
            user_id=hs_user.id,
            record_date=d,
            mood_score=3 + (1 if i > 3 else 0),
            energy_level=3 + (1 if i > 4 else 0),
            stress_level=3 - (1 if i > 3 else 0),
        )
        hs_db.add(mood)

    # 体重数据
    weight = WeightRecord(
        user_id=hs_user.id,
        record_date=today,
        weight=72.0,
        body_fat_percentage=22.0,
        bmi=23.5,
    )
    hs_db.add(weight)
    hs_db.commit()


class TestHealthScoreService:
    def test_calculate_daily_score(self, hs_db, hs_user, hs_service, sample_health_data):
        """测试计算每日健康评分"""
        result = hs_service.calculate_daily_score(hs_db, hs_user.id)
        assert result["status"] == "ok"
        assert "total_score" in result
        assert 0 <= result["total_score"] <= 100
        assert "dimensions" in result
        assert len(result["dimensions"]) > 0

    def test_score_dimensions(self, hs_db, hs_user, hs_service, sample_health_data):
        """测试评分维度"""
        result = hs_service.calculate_daily_score(hs_db, hs_user.id)
        dimensions = {d["name"]: d for d in result["dimensions"]}
        # 应包含运动、睡眠等维度
        assert "运动" in dimensions
        assert "睡眠" in dimensions

        for d in result["dimensions"]:
            assert 0 <= d["score"] <= 100
            assert "weight" in d
            assert "description" in d

    def test_score_no_data(self, hs_db, hs_user, hs_service):
        """测试无数据时的评分"""
        result = hs_service.calculate_daily_score(hs_db, hs_user.id)
        assert result["status"] == "no_data"

    def test_score_trend(self, hs_db, hs_user, hs_service, sample_health_data):
        """测试评分趋势"""
        result = hs_service.get_score_trend(hs_db, hs_user.id, days=7)
        assert "scores" in result
        # 有数据就应该有评分记录
        assert isinstance(result["scores"], list)

    def test_score_trend_empty(self, hs_db, hs_user, hs_service):
        """测试无数据的趋势"""
        result = hs_service.get_score_trend(hs_db, hs_user.id, days=7)
        assert result["scores"] == []

    def test_dimension_weights_sum(self, hs_db, hs_user, hs_service, sample_health_data):
        """测试维度权重之和为1"""
        result = hs_service.calculate_daily_score(hs_db, hs_user.id)
        total_weight = sum(d["weight"] for d in result["dimensions"])
        assert abs(total_weight - 1.0) < 0.01

    def test_score_suggestions(self, hs_db, hs_user, hs_service, sample_health_data):
        """测试评分建议"""
        result = hs_service.calculate_daily_score(hs_db, hs_user.id)
        assert "suggestions" in result
        assert isinstance(result["suggestions"], list)

    def test_partial_data_score(self, hs_db, hs_user, hs_service):
        """测试部分数据的评分"""
        today = date.today()
        # 只有 Garmin 数据
        garmin = GarminData(
            user_id=hs_user.id,
            record_date=today,
            steps=10000,
            sleep_score=80,
            total_sleep_duration=450,
            resting_heart_rate=60,
            stress_level=30,
            body_battery_most_charged=80,
            calories_burned=2200,
        )
        hs_db.add(garmin)
        hs_db.commit()

        result = hs_service.calculate_daily_score(hs_db, hs_user.id)
        assert result["status"] == "ok"
        assert result["total_score"] > 0
