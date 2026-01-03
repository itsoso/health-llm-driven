"""用户API测试"""
import pytest
from datetime import date


def test_create_user(client, sample_user_data):
    """测试创建用户"""
    response = client.post("/api/v1/users", json=sample_user_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == sample_user_data["name"]
    assert data["gender"] == sample_user_data["gender"]
    assert "id" in data


def test_get_users(client, sample_user_data):
    """测试获取用户列表"""
    # 先创建用户
    client.post("/api/v1/users", json=sample_user_data)
    
    # 获取用户列表
    response = client.get("/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_user(client, sample_user_data):
    """测试获取单个用户"""
    # 先创建用户
    create_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = create_response.json()["id"]
    
    # 获取用户
    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["name"] == sample_user_data["name"]


def test_get_nonexistent_user(client):
    """测试获取不存在的用户"""
    response = client.get("/api/v1/users/99999")
    assert response.status_code == 404


def test_create_user_invalid_data(client):
    """测试使用无效数据创建用户"""
    invalid_data = {
        "name": "",  # 空名称
        "birth_date": "invalid-date",  # 无效日期
        "gender": ""
    }
    response = client.post("/api/v1/users", json=invalid_data)
    assert response.status_code == 422  # 验证错误

