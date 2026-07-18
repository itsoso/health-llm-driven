"""目标管理API测试"""
from datetime import date


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


def test_goal_detail_update_delete_are_user_scoped(client, db, auth_user_and_headers):
    """目标详情、更新、删除必须按当前用户隔离。"""
    from tests.conftest import create_authenticated_user

    user, headers = auth_user_and_headers
    other_user, other_token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat(),
    }
    created = client.post("/api/v1/goals", json=goal_data, headers=headers)
    assert created.status_code == 200
    goal_id = created.json()["id"]

    detail = client.get(f"/api/v1/goals/{goal_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["title"] == "每日运动"

    forbidden_detail = client.get(f"/api/v1/goals/{goal_id}", headers=other_headers)
    assert forbidden_detail.status_code == 404

    updated = client.put(
        f"/api/v1/goals/{goal_id}",
        json={"title": "每日快走 30 分钟", "status": "paused", "notes": "膝盖恢复期"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "每日快走 30 分钟"
    assert updated.json()["status"] == "paused"

    forbidden_update = client.put(
        f"/api/v1/goals/{goal_id}",
        json={"title": "越权修改"},
        headers=other_headers,
    )
    assert forbidden_update.status_code == 404

    forbidden_delete = client.delete(f"/api/v1/goals/{goal_id}", headers=other_headers)
    assert forbidden_delete.status_code == 404

    deleted = client.delete(f"/api/v1/goals/{goal_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["record_id"] == goal_id

    detail_after_delete = client.get(f"/api/v1/goals/{goal_id}", headers=headers)
    assert detail_after_delete.status_code == 404


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
        params={"progress_date": progress_date, "progress_value": 25.0},
        headers=headers,
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
        params={"progress_date": progress_date, "progress_value": 25.0},
        headers=headers,
    )

    response = client.get(f"/api/v1/goals/{goal_id}/progress", headers=headers)
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

    response = client.get(f"/api/v1/goals/{goal_id}/completion", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "goal_id" in data
    assert "completion_percentage" in data
    assert "is_completed" in data


def test_goal_progress_and_completion_are_user_scoped(client, db, auth_user_and_headers):
    """目标进展和完成状态同样不得通过猜测 ID 跨用户读取或写入。"""
    from tests.conftest import create_authenticated_user

    user, headers = auth_user_and_headers
    other_user, other_token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {other_token}"}
    created = client.post(
        "/api/v1/goals",
        json={
            "user_id": user.id,
            "goal_type": "exercise",
            "goal_period": "daily",
            "title": "每日运动",
            "target_value": 30.0,
            "target_unit": "分钟",
            "start_date": date.today().isoformat(),
        },
        headers=headers,
    )
    assert created.status_code == 200
    goal_id = created.json()["id"]

    own_update = client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": date.today().isoformat(), "progress_value": 20.0},
        headers=headers,
    )
    assert own_update.status_code == 200

    assert client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": date.today().isoformat(), "progress_value": 30.0},
        headers=other_headers,
    ).status_code == 404
    assert client.get(
        f"/api/v1/goals/{goal_id}/progress", headers=other_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/goals/{goal_id}/completion", headers=other_headers
    ).status_code == 404


def test_goal_generation_has_no_public_user_id_route(client, auth_user_and_headers, monkeypatch):
    """目标自动生成只允许当前用户端点，不能通过 URL 传任意用户 ID。"""
    from app.services.goal_management import GoalManagementService

    user, _ = auth_user_and_headers
    generated_for = []

    def fake_generate(_self, _db, user_id):
        generated_for.append(user_id)
        return []

    monkeypatch.setattr(GoalManagementService, "generate_goals_from_analysis", fake_generate)

    response = client.post(f"/api/v1/goals/generate-from-analysis/{user.id}")

    assert response.status_code == 404
    assert generated_for == []
