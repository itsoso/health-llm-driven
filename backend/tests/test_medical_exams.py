"""体检数据API测试"""
import pytest


def test_create_medical_exam(client, sample_user_data, sample_medical_exam_data):
    """测试创建体检记录"""
    # 先创建用户
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    sample_medical_exam_data["user_id"] = user_id
    
    # 创建体检记录
    response = client.post("/api/v1/medical-exams", json=sample_medical_exam_data)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["exam_type"] == sample_medical_exam_data["exam_type"]
    assert len(data["items"]) == len(sample_medical_exam_data["items"])


def test_get_user_medical_exams(client, sample_user_data, sample_medical_exam_data):
    """测试获取用户的体检记录"""
    # 创建用户和体检记录
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    sample_medical_exam_data["user_id"] = user_id
    
    client.post("/api/v1/medical-exams", json=sample_medical_exam_data)
    
    # 获取体检记录
    response = client.get(f"/api/v1/medical-exams/user/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_import_medical_exam_from_json(client, sample_user_data):
    """测试从JSON导入体检数据"""
    # 创建用户
    user_response = client.post("/api/v1/users", json=sample_user_data)
    user_id = user_response.json()["id"]
    
    # 准备导入数据
    import_data = {
        "exam": {
            "exam_date": "2024-01-01",
            "exam_type": "blood_routine",
            "body_system": "circulatory",
            "hospital_name": "测试医院"
        },
        "items": [
            {
                "item_name": "白细胞",
                "value": 6.5,
                "unit": "10^9/L",
                "reference_range": "3.5-9.5",
                "result": "正常",
                "is_abnormal": "normal"
            }
        ]
    }
    
    response = client.post(
        f"/api/v1/medical-exams/import/json?user_id={user_id}",
        json=import_data
    )
    assert response.status_code == 200
    data = response.json()
    assert "exam_id" in data

