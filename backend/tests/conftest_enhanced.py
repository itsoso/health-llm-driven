"""
增强的测试配置和 fixtures
提供更多测试工具和数据 fixtures
"""

import os
import pytest
from unittest.mock import Mock, MagicMock
from datetime import date, datetime, timedelta
from typing import Dict, Any, List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

# 设置测试环境变量
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("ENVIRONMENT", "test")

from app.database import Base, get_db
from main import app

# 使用内存数据库进行测试
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ==================== 数据库 Fixtures ====================

@pytest.fixture(scope="function")
def test_db():
    """创建测试数据库会话"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def mock_db():
    """Mock 数据库会话（用于不需要真实数据库的测试）"""
    db = Mock(spec=Session)
    return db


# ==================== API 客户端 Fixtures ====================

@pytest.fixture(scope="function")
def test_client(test_db):
    """创建测试 API 客户端"""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# ==================== 用户相关 Fixtures ====================

@pytest.fixture
def mock_user():
    """Mock 用户对象"""
    from app.models.user import User
    user = Mock(spec=User)
    user.id = 1
    user.email = "test@example.com"
    user.nickname = "测试用户"
    user.is_active = True
    user.is_approved = True
    user.created_at = datetime.now()
    return user


@pytest.fixture
def mock_user_profile():
    """Mock 用户画像"""
    from app.models.user_profile import UserProfile
    profile = Mock(spec=UserProfile)
    profile.id = 1
    profile.user_id = 1
    profile.age = 35
    profile.gender = "male"
    profile.birth_date = date(1990, 1, 1)
    profile.height_cm = 175
    profile.current_weight_kg = 70
    profile.target_weight_kg = 68
    profile.bmi = 22.86
    profile.bmi_category = "正常"
    profile.blood_type = "O"
    profile.allergies = []
    profile.chronic_conditions = []
    profile.family_history = []
    profile.exercise_frequency = "daily"
    profile.diet_preference = "normal"
    profile.smoking_status = "never"
    profile.alcohol_consumption = "occasionally"
    profile.city = "杭州"
    profile.timezone = "Asia/Shanghai"
    return profile


@pytest.fixture
def test_user_data():
    """测试用户数据"""
    return {
        "email": "test@example.com",
        "nickname": "测试用户",
        "password": "Test123!@#",
        "is_active": True,
        "is_approved": True
    }


# ==================== 健康数据 Fixtures ====================

@pytest.fixture
def mock_garmin_data():
    """Mock Garmin 健康数据"""
    from app.models.daily_health import GarminData
    data = Mock(spec=GarminData)
    data.id = 1
    data.user_id = 1
    data.record_date = date.today()

    # 睡眠数据
    data.sleep_score = 85
    data.total_sleep_duration = 450  # 7.5小时（分钟）
    data.deep_sleep_duration = 120
    data.rem_sleep_duration = 90
    data.light_sleep_duration = 180
    data.awake_duration = 60

    # 心率数据
    data.avg_heart_rate = 65
    data.max_heart_rate = 150
    data.min_heart_rate = 45
    data.resting_heart_rate = 55
    data.hrv = 45.5
    data.hrv_status = "balanced"

    # 压力和能量
    data.stress_level = 35
    data.body_battery = 75
    data.body_battery_charged = 80
    data.body_battery_drained = 5

    # 活动数据
    data.steps = 8500
    data.calories_burned = 2200
    data.active_minutes = 45
    data.intensity_minutes = 30

    return data


@pytest.fixture
def mock_garmin_data_list():
    """Mock Garmin 数据列表（最近7天）"""
    from app.models.daily_health import GarminData
    data_list = []
    for i in range(7):
        data = Mock(spec=GarminData)
        data.record_date = date.today() - timedelta(days=i)
        data.sleep_score = 80 + i
        data.total_sleep_duration = 420 + i * 10
        data.stress_level = 30 + i
        data.resting_heart_rate = 55 + i
        data.steps = 8000 + i * 100
        data.body_battery = 70 + i
        data_list.append(data)
    return data_list


@pytest.fixture
def test_basic_health_data():
    """测试基础健康数据"""
    return {
        "user_id": 1,
        "height": 175.0,
        "weight": 70.0,
        "bmi": 22.86,
        "systolic_bp": 120,
        "diastolic_bp": 80,
        "heart_rate": 70,
        "record_date": str(date.today()),
        "notes": "测试数据"
    }


# ==================== 运动数据 Fixtures ====================

@pytest.fixture
def mock_workout_record():
    """Mock 运动记录"""
    from app.models.daily_health import WorkoutRecord
    workout = Mock(spec=WorkoutRecord)
    workout.id = 1
    workout.user_id = 1
    workout.workout_date = date.today()
    workout.workout_type = "running"
    workout.workout_name = "晨跑"
    workout.duration_minutes = 45
    workout.calories = 450
    workout.avg_heart_rate = 145
    workout.max_heart_rate = 175
    workout.distance_km = 6.5
    workout.avg_pace = "6:55"
    workout.elevation_gain = 50
    workout.training_effect = 3.5
    workout.intensity = "moderate"
    return workout


@pytest.fixture
def mock_workout_list():
    """Mock 运动记录列表"""
    from app.models.daily_health import WorkoutRecord
    workouts = []
    workout_types = ["running", "cycling", "swimming", "strength"]

    for i in range(4):
        workout = Mock(spec=WorkoutRecord)
        workout.workout_date = date.today() - timedelta(days=i)
        workout.workout_type = workout_types[i]
        workout.duration_minutes = 30 + i * 10
        workout.calories = 300 + i * 50
        workout.avg_heart_rate = 140 + i * 5
        workouts.append(workout)

    return workouts


# ==================== 饮食数据 Fixtures ====================

@pytest.fixture
def mock_diet_record():
    """Mock 饮食记录"""
    from app.models.daily_health import DietRecord
    diet = Mock(spec=DietRecord)
    diet.id = 1
    diet.user_id = 1
    diet.record_date = date.today()
    diet.meal_type = "breakfast"
    diet.meal_time = datetime.now().time()
    diet.food_name = "燕麦粥"
    diet.food_items = "燕麦,牛奶,香蕉"
    diet.calories = 500
    diet.protein = 25
    diet.carbs = 60
    diet.fat = 15
    diet.fiber = 10
    return diet


@pytest.fixture
def mock_diet_list():
    """Mock 饮食记录列表"""
    from app.models.daily_health import DietRecord
    diets = []
    meal_types = ["breakfast", "lunch", "dinner", "snack"]

    for i, meal_type in enumerate(meal_types):
        diet = Mock(spec=DietRecord)
        diet.record_date = date.today()
        diet.meal_type = meal_type
        diet.calories = 400 + i * 100
        diet.protein = 20 + i * 5
        diet.carbs = 50 + i * 10
        diet.fat = 10 + i * 5
        diets.append(diet)

    return diets


# ==================== 补剂数据 Fixtures ====================

@pytest.fixture
def mock_supplement_definition():
    """Mock 补剂定义"""
    from app.models.supplement import SupplementDefinition
    supplement = Mock(spec=SupplementDefinition)
    supplement.id = 1
    supplement.user_id = 1
    supplement.name = "维生素D"
    supplement.dosage = "2000IU"
    supplement.timing = "morning"
    supplement.category = "vitamin"
    supplement.description = "补充维生素D"
    supplement.is_active = True
    supplement.created_at = datetime.now()
    return supplement


@pytest.fixture
def mock_supplement_list():
    """Mock 补剂定义列表"""
    from app.models.supplement import SupplementDefinition
    supplements = []
    supplement_data = [
        ("维生素D", "2000IU", "morning", "vitamin"),
        ("鱼油", "1000mg", "breakfast", "omega3"),
        ("蛋白粉", "30g", "post_workout", "protein"),
        ("镁", "400mg", "bedtime", "mineral")
    ]

    for i, (name, dosage, timing, category) in enumerate(supplement_data):
        supplement = Mock(spec=SupplementDefinition)
        supplement.id = i + 1
        supplement.name = name
        supplement.dosage = dosage
        supplement.timing = timing
        supplement.category = category
        supplement.is_active = True
        supplements.append(supplement)

    return supplements


@pytest.fixture
def mock_supplement_record():
    """Mock 补剂服用记录"""
    from app.models.supplement import SupplementRecord
    record = Mock(spec=SupplementRecord)
    record.id = 1
    record.user_id = 1
    record.supplement_id = 1
    record.record_date = date.today()
    record.taken = True
    record.taken_time = datetime.now()
    return record


# ==================== LLM 相关 Fixtures ====================

@pytest.fixture
def mock_llm_response():
    """Mock LLM 响应"""
    return {
        "analysis": "用户健康状况良好，睡眠质量优秀，运动量适中。",
        "recommendations": [
            {
                "name": "维生素D",
                "reason": "睡眠质量良好，但可能缺乏日照",
                "dosage": "2000IU",
                "timing": "早餐后",
                "priority": "中",
                "icon": "☀️",
                "category": "vitamin"
            },
            {
                "name": "镁",
                "reason": "有助于改善睡眠质量和肌肉恢复",
                "dosage": "400mg",
                "timing": "睡前",
                "priority": "中",
                "icon": "💊",
                "category": "mineral"
            }
        ],
        "timing_suggestions": {
            "morning": ["维生素D"],
            "noon": [],
            "evening": [],
            "bedtime": ["镁"],
            "workout": []
        },
        "precautions": [
            "请在医生指导下服用补剂",
            "注意观察身体反应",
            "定期复查相关指标"
        ],
        "overall_rating": {
            "score": 8,
            "rating": "优秀",
            "emoji": "🌟",
            "message": "您的补剂方案科学合理"
        }
    }


@pytest.fixture
def mock_digital_twin_service():
    """Mock DigitalTwin 服务"""
    service = Mock()
    service.analyze_supplement_needs.return_value = {
        "recommendations": []
    }
    service.analyze_diet_needs.return_value = {
        "recommendations": []
    }
    return service


# ==================== 时间相关 Fixtures ====================

@pytest.fixture
def today():
    """今天的日期"""
    return date.today()


@pytest.fixture
def yesterday():
    """昨天的日期"""
    return date.today() - timedelta(days=1)


@pytest.fixture
def last_week():
    """一周前的日期"""
    return date.today() - timedelta(days=7)


@pytest.fixture
def date_range_7days():
    """最近7天的日期列表"""
    return [date.today() - timedelta(days=i) for i in range(7)]


# ==================== 测试工具函数 ====================

@pytest.fixture
def assert_response_success():
    """断言响应成功的辅助函数"""
    def _assert(response):
        assert response.status_code == 200
        data = response.json()
        assert "success" in data or "data" in data
        return data
    return _assert


@pytest.fixture
def assert_response_error():
    """断言响应错误的辅助函数"""
    def _assert(response, expected_status=400):
        assert response.status_code == expected_status
        data = response.json()
        assert "detail" in data or "error" in data
        return data
    return _assert


@pytest.fixture
def create_test_user(test_db):
    """创建测试用户的辅助函数"""
    def _create(email="test@example.com", **kwargs):
        from app.models.user import User
        from app.services.auth import get_password_hash

        user = User(
            email=email,
            hashed_password=get_password_hash("Test123!@#"),
            nickname=kwargs.get("nickname", "测试用户"),
            is_active=kwargs.get("is_active", True),
            is_approved=kwargs.get("is_approved", True)
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user
    return _create


# ==================== Pytest 配置 ====================

def pytest_configure(config):
    """Pytest 配置"""
    config.addinivalue_line(
        "markers", "integration: 标记为集成测试"
    )
    config.addinivalue_line(
        "markers", "slow: 标记为慢速测试"
    )
    config.addinivalue_line(
        "markers", "llm: 标记为需要 LLM 的测试"
    )


# ==================== 测试日志配置 ====================

@pytest.fixture(scope="session", autouse=True)
def configure_test_logging():
    """配置测试日志"""
    import logging

    # 设置测试日志级别
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    # 禁用某些库的详细日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


# ==================== 使用示例 ====================

"""
在测试中使用这些 fixtures：

def test_example(mock_user, mock_garmin_data, mock_llm_response):
    # 使用 mock 数据进行测试
    assert mock_user.id == 1
    assert mock_garmin_data.sleep_score == 85
    assert len(mock_llm_response["recommendations"]) == 2

def test_with_real_db(test_db, create_test_user):
    # 使用真实数据库
    user = create_test_user(email="real@example.com")
    assert user.id is not None

def test_api_endpoint(test_client, assert_response_success):
    # 测试 API 端点
    response = test_client.get("/api/v1/health/status")
    data = assert_response_success(response)
    assert "status" in data
"""
