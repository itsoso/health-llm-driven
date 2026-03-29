"""用户API测试"""
import pytest
import uuid
from datetime import date
from app.models.user import User
from app.services.auth import auth_service


def create_admin_user(db):
    """创建管理员用户并返回 (user, headers)"""
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
    return admin, {"Authorization": f"Bearer {token}"}


def test_create_user(client, db, sample_user_data):
    """测试创建用户（管理员）"""
    _, headers = create_admin_user(db)
    response = client.post("/api/v1/users", json=sample_user_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == sample_user_data["name"]
    assert data["gender"] == sample_user_data["gender"]
    assert "id" in data


def test_create_user_no_auth(client, sample_user_data):
    """测试无认证创建用户应 401"""
    response = client.post("/api/v1/users", json=sample_user_data)
    assert response.status_code == 401


def test_create_user_non_admin(client, db, sample_user_data):
    """测试非管理员创建用户应 403"""
    from tests.conftest import create_authenticated_user
    _, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/users", json=sample_user_data, headers=headers)
    assert response.status_code == 403


def test_get_users(client, db, sample_user_data):
    """测试获取用户列表（管理员）"""
    _, headers = create_admin_user(db)
    # 先创建用户
    client.post("/api/v1/users", json=sample_user_data, headers=headers)

    # 获取用户列表
    response = client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_user(client, db, sample_user_data):
    """测试获取单个用户（管理员）"""
    _, headers = create_admin_user(db)
    create_response = client.post("/api/v1/users", json=sample_user_data, headers=headers)
    user_id = create_response.json()["id"]

    response = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["name"] == sample_user_data["name"]


def test_get_nonexistent_user(client, db):
    """测试获取不存在的用户"""
    _, headers = create_admin_user(db)
    response = client.get("/api/v1/users/99999", headers=headers)
    assert response.status_code == 404


def test_create_user_invalid_data(client, db):
    """测试使用无效数据创建用户"""
    _, headers = create_admin_user(db)
    invalid_data = {
        "name": "",  # 空名称
        "birth_date": "invalid-date",  # 无效日期
        "gender": ""
    }
    response = client.post("/api/v1/users", json=invalid_data, headers=headers)
    assert response.status_code == 422  # 验证错误
