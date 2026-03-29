"""基础健康数据API测试"""
import pytest
import uuid
from datetime import date
from app.models.user import User
from app.services.auth import auth_service


def _create_admin_and_user(db, client):
    """创建管理员，然后用管理员创建一个普通用户，返回 (user_id, admin_headers)"""
    admin = User(
        username=f"admin_{uuid.uuid4().hex[:8]}",
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        name="管理员",
        birth_date=date(1990, 1, 1),
        gender="男",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    token = auth_service.create_access_token({"sub": str(admin.id)})
    headers = {"Authorization": f"Bearer {token}"}

    sample_user_data = {"name": "测试用户", "birth_date": "1990-01-01", "gender": "男"}
    user_response = client.post("/api/v1/users", json=sample_user_data, headers=headers)
    user_id = user_response.json()["id"]
    return user_id, headers


def test_create_basic_health_data(client, db, sample_basic_health_data):
    """测试创建基础健康数据"""
    user_id, headers = _create_admin_and_user(db, client)
    sample_basic_health_data["user_id"] = user_id

    response = client.post("/api/v1/basic-health", json=sample_basic_health_data)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["height"] == sample_basic_health_data["height"]
    assert data["weight"] == sample_basic_health_data["weight"]


def test_get_user_basic_health_data(client, db, sample_basic_health_data):
    """测试获取用户的基础健康数据"""
    user_id, headers = _create_admin_and_user(db, client)
    sample_basic_health_data["user_id"] = user_id

    client.post("/api/v1/basic-health", json=sample_basic_health_data)

    response = client.get(f"/api/v1/basic-health/user/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_latest_basic_health_data(client, db, sample_basic_health_data):
    """测试获取最新的基础健康数据"""
    user_id, headers = _create_admin_and_user(db, client)
    sample_basic_health_data["user_id"] = user_id

    client.post("/api/v1/basic-health", json=sample_basic_health_data)

    response = client.get(f"/api/v1/basic-health/user/{user_id}/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id


def test_bmi_auto_calculation(client, db):
    """测试BMI自动计算"""
    user_id, headers = _create_admin_and_user(db, client)

    health_data = {
        "user_id": user_id,
        "height": 175.0,
        "weight": 70.0,
        "record_date": "2024-01-01"
    }

    response = client.post("/api/v1/basic-health", json=health_data)
    assert response.status_code == 200
    data = response.json()
    assert data["bmi"] is not None
    assert abs(data["bmi"] - 22.86) < 0.01
