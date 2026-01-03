"""测试配置和fixtures"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.database import Base, get_db
from main import app

# 使用内存数据库进行测试
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """创建测试数据库"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """创建测试客户端"""
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_user_data():
    """示例用户数据"""
    return {
        "name": "测试用户",
        "birth_date": "1990-01-01",
        "gender": "男"
    }


@pytest.fixture
def sample_basic_health_data():
    """示例基础健康数据"""
    return {
        "user_id": 1,
        "height": 175.0,
        "weight": 70.0,
        "bmi": 22.86,
        "systolic_bp": 120,
        "diastolic_bp": 80,
        "total_cholesterol": 5.0,
        "ldl_cholesterol": 3.0,
        "hdl_cholesterol": 1.5,
        "triglycerides": 1.2,
        "blood_glucose": 5.5,
        "record_date": "2024-01-01",
        "notes": "测试数据"
    }


@pytest.fixture
def sample_medical_exam_data():
    """示例体检数据"""
    return {
        "user_id": 1,
        "exam_date": "2024-01-01",
        "exam_type": "blood_routine",
        "body_system": "circulatory",
        "hospital_name": "测试医院",
        "doctor_name": "测试医生",
        "overall_assessment": "总体良好",
        "items": [
            {
                "item_name": "白细胞",
                "value": 6.5,
                "unit": "10^9/L",
                "reference_range": "3.5-9.5",
                "result": "正常",
                "is_abnormal": "normal"
            },
            {
                "item_name": "红细胞",
                "value": 4.5,
                "unit": "10^12/L",
                "reference_range": "4.0-5.5",
                "result": "正常",
                "is_abnormal": "normal"
            }
        ]
    }

