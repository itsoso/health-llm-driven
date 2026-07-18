"""集成测试"""
from datetime import date


def test_full_user_workflow(client, auth_user_and_headers, sample_basic_health_data):
    """测试完整的用户工作流程"""
    user, headers = auth_user_and_headers

    # 2. 录入基础健康数据
    sample_basic_health_data["user_id"] = user.id
    health_response = client.post(
        "/api/v1/basic-health", json=sample_basic_health_data, headers=headers
    )
    assert health_response.status_code == 200

    # 3. 创建目标
    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动30分钟",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat()
    }
    goal_response = client.post("/api/v1/goals", json=goal_data, headers=headers)
    assert goal_response.status_code == 200
    goal_id = goal_response.json()["id"]

    # 4. 更新目标进展
    progress_response = client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": date.today().isoformat(), "progress_value": 25.0},
        headers=headers,
    )
    assert progress_response.status_code == 200

    # 5. 进行健康打卡
    checkin_data = {
        "user_id": user.id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0,
        "running_duration": 30
    }
    checkin_response = client.post("/api/v1/checkin", json=checkin_data, headers=headers)
    assert checkin_response.status_code == 200

    # 6. 获取今日打卡
    today_checkin = client.get(f"/api/v1/checkin/user/{user.id}/today", headers=headers)
    assert today_checkin.status_code == 200
    assert today_checkin.json()["running_distance"] == 5.0


def test_health_analysis_workflow(client, auth_user_and_headers, sample_basic_health_data, sample_medical_exam_data):
    """测试健康分析工作流程"""
    user, headers = auth_user_and_headers

    sample_basic_health_data["user_id"] = user.id
    client.post("/api/v1/basic-health", json=sample_basic_health_data, headers=headers)

    sample_medical_exam_data["user_id"] = user.id
    client.post("/api/v1/medical-exams", json=sample_medical_exam_data, headers=headers)

    # 2. 进行健康分析
    analysis_response = client.get(f"/api/v1/analysis/user/{user.id}/issues", headers=headers)
    assert analysis_response.status_code == 200


def test_goal_completion_tracking(client, auth_user_and_headers):
    """测试目标完成追踪"""
    user, headers = auth_user_and_headers

    goal_data = {
        "user_id": user.id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动30分钟",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat()
    }
    goal_response = client.post("/api/v1/goals", json=goal_data, headers=headers)
    assert goal_response.status_code == 200
    goal_id = goal_response.json()["id"]

    # 更新进展（未完成）
    client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": date.today().isoformat(), "progress_value": 25.0},
        headers=headers,
    )

    completion = client.get(f"/api/v1/goals/{goal_id}/completion", headers=headers)
    assert completion.status_code == 200
    completion_data = completion.json()
    assert not completion_data["is_completed"]
    assert completion_data["completion_percentage"] < 100

    # 更新进展（完成）
    client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": date.today().isoformat(), "progress_value": 30.0},
        headers=headers,
    )

    completion = client.get(f"/api/v1/goals/{goal_id}/completion", headers=headers)
    completion_data = completion.json()
    assert completion_data["is_completed"]
    assert completion_data["completion_percentage"] >= 100
