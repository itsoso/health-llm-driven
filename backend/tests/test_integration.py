"""集成测试"""
import pytest
from datetime import date


def test_full_user_workflow(client, sample_user_data, sample_basic_health_data):
    """测试完整的用户工作流程"""
    # 1. 创建用户
    user_response = client.post("/api/v1/users", json=sample_user_data)
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]
    
    # 2. 录入基础健康数据
    sample_basic_health_data["user_id"] = user_id
    health_response = client.post("/api/v1/basic-health", json=sample_basic_health_data)
    assert health_response.status_code == 200
    
    # 3. 创建目标
    goal_data = {
        "user_id": user_id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动30分钟",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat()
    }
    goal_response = client.post("/api/v1/goals", json=goal_data)
    assert goal_response.status_code == 200
    goal_id = goal_response.json()["id"]
    
    # 4. 更新目标进展
    progress_response = client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": date.today().isoformat(), "progress_value": 25.0}
    )
    assert progress_response.status_code == 200
    
    # 5. 进行健康打卡
    checkin_data = {
        "user_id": user_id,
        "checkin_date": date.today().isoformat(),
        "running_distance": 5.0,
        "running_duration": 30
    }
    checkin_response = client.post("/api/v1/checkin", json=checkin_data)
    assert checkin_response.status_code == 200
    
    # 6. 获取今日打卡
    today_checkin = client.get(f"/api/v1/checkin/user/{user_id}/today")
    assert today_checkin.status_code == 200
    assert today_checkin.json()["running_distance"] == 5.0


def test_health_analysis_workflow(client, sample_user_data, sample_basic_health_data, sample_medical_exam_data):
    """测试健康分析工作流程"""
    # 1. 创建用户和数据
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    sample_basic_health_data["user_id"] = user_id
    client.post("/api/v1/basic-health", json=sample_basic_health_data)
    
    sample_medical_exam_data["user_id"] = user_id
    client.post("/api/v1/medical-exams", json=sample_medical_exam_data)
    
    # 2. 进行健康分析
    analysis_response = client.get(f"/api/v1/analysis/user/{user_id}/issues")
    assert analysis_response.status_code == 200
    # 注意：如果没有配置OpenAI API，会返回错误信息，但状态码仍然是200


def test_goal_completion_tracking(client, sample_user_data):
    """测试目标完成追踪"""
    # 创建用户和目标
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    goal_data = {
        "user_id": user_id,
        "goal_type": "exercise",
        "goal_period": "daily",
        "title": "每日运动30分钟",
        "target_value": 30.0,
        "target_unit": "分钟",
        "start_date": date.today().isoformat()
    }
    goal_response = client.post("/api/v1/goals", json=goal_data)
    goal_id = goal_response.json()["id"]
    
    # 更新进展（未完成）
    client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": date.today().isoformat(), "progress_value": 25.0}
    )
    
    completion = client.get(f"/api/v1/goals/{goal_id}/completion")
    assert completion.status_code == 200
    completion_data = completion.json()
    assert completion_data["is_completed"] == False
    assert completion_data["completion_percentage"] < 100
    
    # 更新进展（完成）
    client.post(
        f"/api/v1/goals/{goal_id}/progress",
        params={"progress_date": date.today().isoformat(), "progress_value": 30.0}
    )
    
    completion = client.get(f"/api/v1/goals/{goal_id}/completion")
    completion_data = completion.json()
    assert completion_data["is_completed"] == True
    assert completion_data["completion_percentage"] >= 100

