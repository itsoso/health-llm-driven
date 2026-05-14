"""测试配置和fixtures"""
import os
import uuid
import tempfile
import pytest
from datetime import date
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.database import Base, get_db
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=")

from main import app


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    """测试库使用 SQLite, 将 PostgreSQL JSONB 降级成 JSON."""
    return "JSON"


@pytest.fixture(scope="function")
def db():
    """创建测试数据库 - 每个测试使用独立的内存数据库"""
    import app.models  # noqa: F401 - ensure all model tables/columns are registered before create_all

    # 使用 StaticPool 确保所有连接使用同一个内存数据库
    # 使用 check_same_thread=False 允许多线程访问
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    # 清除可能存在的元数据缓存
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


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


def create_authenticated_user(db):
    """创建一个已认证的测试用户，返回 (user, token)"""
    from app.models.user import User
    from app.services.auth import auth_service

    user = User(
        username=f"testuser_{uuid.uuid4().hex[:8]}",
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        name="测试用户",
        birth_date=date(1990, 1, 1),
        gender="男",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, token


@pytest.fixture
def auth_user_and_headers(db):
    """创建已认证用户，返回 (user, headers)"""
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


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
