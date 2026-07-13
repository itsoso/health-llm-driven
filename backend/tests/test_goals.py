"""目标管理API测试"""
import pytest
from datetime import date, timedelta


def test_create_goal(client, auth_user_and_headers):
    """测试创建目标"""
    user, headers = auth_user_and_headers

    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动30分钟",
        "description": "保持每日适量运动",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat(),
        "implementation_steps": "1. 每天至少30分钟中等强度运动\n2. 可以分多次完成",
        "priority": 7
    }

    response = client.post("/api/v1/goals", json=goal_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == goal_data["title"]
    assert data["target_value"] == goal_data["target_value"]


def test_update_goal(client, auth_user_and_headers):
    """目标本体可修改,供小巴执行'把目标改成...'。"""
    user, headers = auth_user_and_headers

    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动30分钟",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat(),
        "priority": 7,
    }
    create_response = client.post("/api/v1/goals", json=goal_data, headers=headers)
    goal_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/goals/{goal_id}",
        json={"title": "每日运动40分钟", "target_value": 40.0, "priority": 6},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == goal_id
    assert data["title"] == "每日运动40分钟"
    assert data["target_value"] == 40.0
    assert data["priority"] == 6


def test_delete_goal(client, auth_user_and_headers):
    """目标本体可删除,供 agent 撤销误建目标。"""
    user, headers = auth_user_and_headers

    goal_data = {
        "user_id": user.id,
        "goal_type": "water",
        "goal_period": "daily",
        "title": "每天喝水2000ml",
        "target_value": 2000.0,
        "target_unit": "ml",
        "start_date": date.today().isoformat(),
    }
    create_response = client.post("/api/v1/goals", json=goal_data, headers=headers)
    goal_id = create_response.json()["id"]

    response = client.delete(f"/api/v1/goals/{goal_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["goal_id"] == goal_id
    assert client.get("/api/v1/goals/me", headers=headers).json() == []


def test_get_user_goals(client, auth_user_and_headers):
    """测试获取用户目标"""
    user, headers = auth_user_and_headers

    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat()
    }
    client.post("/api/v1/goals", json=goal_data, headers=headers)

    response = client.get(f"/api/v1/goals/user/{user.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_update_goal_progress(client, auth_user_and_headers):
    """测试更新目标进展"""
    user, headers = auth_user_and_headers

    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat()
    }
    goal_response = client.post("/api/v1/goals", json=goal_data, headers=headers)
    goal_id = goal_response.json()["id"]

    progress_date = date.today().isoformat()
    response = client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": progress_date, "progress_value": 25.0}
    )
    assert response.status_code == 200
    data = response.json()
    assert "progress_id" in data


def test_get_goal_progress(client, auth_user_and_headers):
    """测试获取目标进展"""
    user, headers = auth_user_and_headers

    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat()
    }
    goal_response = client.post("/api/v1/goals", json=goal_data, headers=headers)
    goal_id = goal_response.json()["id"]

    progress_date = date.today().isoformat()
    client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": progress_date, "progress_value": 25.0}
    )

    response = client.get(f"/api/v1/goals/{goal_id}/progress")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_check_goal_completion(client, auth_user_and_headers):
    """测试检查目标完成情况"""
    user, headers = auth_user_and_headers

    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat()
    }
    goal_response = client.post("/api/v1/goals", json=goal_data, headers=headers)
    goal_id = goal_response.json()["id"]

    response = client.get(f"/api/v1/goals/{goal_id}/completion")
    assert response.status_code == 200
    data = response.json()
    assert "goal_id" in data
    assert "completion_percentage" in data
    assert "is_completed" in data
