"""健康打卡API测试"""
import pytest
from datetime import date


def test_create_health_checkin(client, auth_user_and_headers):
    """测试创建健康打卡"""
    user, headers = auth_user_and_headers

    checkin_data = {
        "user_id": user.id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0,
        "running_duration": 30,
        "squats_count": 50,
        "tai_chi_duration": 20,
        "ba_duan_jin_duration": 15,
        "notes": "今日运动完成"
    }

    response = client.post("/api/v1/checkin", json=checkin_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user.id
    assert data["running_distance"] == checkin_data["running_distance"]


def test_get_user_checkins(client, auth_user_and_headers):
    """测试获取用户打卡记录"""
    user, headers = auth_user_and_headers

    checkin_data = {
        "user_id": user.id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0
    }
    client.post("/api/v1/checkin", json=checkin_data, headers=headers)

    response = client.get(f"/api/v1/checkin/user/{user.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_today_checkin(client, auth_user_and_headers):
    """测试获取今日打卡"""
    user, headers = auth_user_and_headers

    checkin_data = {
        "user_id": user.id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0
    }
    client.post("/api/v1/checkin", json=checkin_data, headers=headers)

    response = client.get(f"/api/v1/checkin/user/{user.id}/today", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["checkin_date"] == date.today().isoformat()


def test_update_existing_checkin(client, auth_user_and_headers):
    """测试更新已存在的打卡"""
    user, headers = auth_user_and_headers

    checkin_data = {
        "user_id": user.id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0
    }
    client.post("/api/v1/checkin", json=checkin_data, headers=headers)

    updated_data = {
        "user_id": user.id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 8.0,
        "squats_count": 100
    }
    response = client.post("/api/v1/checkin", json=updated_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["running_distance"] == 8.0
    assert data["squats_count"] == 100
