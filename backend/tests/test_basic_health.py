"""基础健康数据API测试"""
import pytest


def test_create_basic_health_data(client, sample_user_data, sample_basic_health_data):
    """测试创建基础健康数据"""
    # 先创建用户
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    sample_basic_health_data["user_id"] = user_id
    
    # 创建基础健康数据
    response = client.post("/api/v1/basic-health", json=sample_basic_health_data)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["height"] == sample_basic_health_data["height"]
    assert data["weight"] == sample_basic_health_data["weight"]


def test_get_user_basic_health_data(client, sample_user_data, sample_basic_health_data):
    """测试获取用户的基础健康数据"""
    # 创建用户和数据
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    sample_basic_health_data["user_id"] = user_id
    
    client.post("/api/v1/basic-health", json=sample_basic_health_data)
    
    # 获取数据
    response = client.get(f"/api/v1/basic-health/user/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_latest_basic_health_data(client, sample_user_data, sample_basic_health_data):
    """测试获取最新的基础健康数据"""
    # 创建用户和数据
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    sample_basic_health_data["user_id"] = user_id
    
    client.post("/api/v1/basic-health", json=sample_basic_health_data)
    
    # 获取最新数据
    response = client.get(f"/api/v1/basic-health/user/{user_id}/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id


def test_bmi_auto_calculation(client, sample_user_data):
    """测试BMI自动计算"""
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    # 创建数据时不提供BMI
    health_data = {
        "user_id": user_id,
        "height": 175.0,
        "weight": 70.0,
        "record_date": "2024-01-01"
    }
    
    response = client.post("/api/v1/basic-health", json=health_data)
    assert response.status_code == 200
    data = response.json()
    # 验证BMI被自动计算
    assert data["bmi"] is not None
    assert abs(data["bmi"] - 22.86) < 0.01  # 70 / (1.75^2) ≈ 22.86

