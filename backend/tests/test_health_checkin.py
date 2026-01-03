"""健康打卡API测试"""
import pytest
from datetime import date


def test_create_health_checkin(client, sample_user_data):
    """测试创建健康打卡"""
    # 创建用户
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    # 创建打卡
    checkin_data = {
        "user_id": user_id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0,
        "running_duration": 30,
        "squats_count": 50,
        "tai_chi_duration": 20,
        "ba_duan_jin_duration": 15,
        "notes": "今日运动完成"
    }
    
    response = client.post("/api/v1/checkin", json=checkin_data)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["running_distance"] == checkin_data["running_distance"]


def test_get_user_checkins(client, sample_user_data):
    """测试获取用户打卡记录"""
    # 创建用户和打卡
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    checkin_data = {
        "user_id": user_id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0
    }
    client.post("/api/v1/checkin", json=checkin_data)
    
    # 获取打卡记录
    response = client.get(f"/api/v1/checkin/user/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_today_checkin(client, sample_user_data):
    """测试获取今日打卡"""
    # 创建用户和打卡
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    checkin_data = {
        "user_id": user_id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0
    }
    client.post("/api/v1/checkin", json=checkin_data)
    
    # 获取今日打卡
    response = client.get(f"/api/v1/checkin/user/{user_id}/today")
    assert response.status_code == 200
    data = response.json()
    assert data["checkin_date"] == date.today().isoformat()


def test_update_existing_checkin(client, sample_user_data):
    """测试更新已存在的打卡"""
    # 创建用户和打卡
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    checkin_data = {
        "user_id": user_id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0
    }
    client.post("/api/v1/checkin", json=checkin_data)
    
    # 更新打卡
    updated_data = {
        "user_id": user_id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 8.0,  # 更新距离
        "squats_count": 100  # 新增数据
    }
    response = client.post("/api/v1/checkin", json=updated_data)
    assert response.status_code == 200
    data = response.json()
    assert data["running_distance"] == 8.0
    assert data["squats_count"] == 100

