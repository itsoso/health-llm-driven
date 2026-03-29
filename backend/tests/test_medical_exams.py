"""体检数据API测试"""
import pytest
import uuid
from datetime import date
from app.models.user import User
from app.services.auth import auth_service


def _create_admin_and_user(db, client):
    """创建管理员，然后用管理员创建一个普通用户，返回 (user_id, admin_headers)"""
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
    headers = {"Authorization": f"Bearer {token}"}

    sample_user_data = {"name": "测试用户", "birth_date": "1990-01-01", "gender": "男"}
    user_response = client.post("/api/v1/users", json=sample_user_data, headers=headers)
    user_id = user_response.json()["id"]
    return user_id, headers


def test_create_medical_exam(client, db, sample_medical_exam_data):
    """测试创建体检记录"""
    user_id, headers = _create_admin_and_user(db, client)
    sample_medical_exam_data["user_id"] = user_id

    response = client.post("/api/v1/medical-exams", json=sample_medical_exam_data)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["exam_type"] == sample_medical_exam_data["exam_type"]
    assert len(data["items"]) == len(sample_medical_exam_data["items"])


def test_get_user_medical_exams(client, db, sample_medical_exam_data):
    """测试获取用户的体检记录"""
    user_id, headers = _create_admin_and_user(db, client)
    sample_medical_exam_data["user_id"] = user_id

    client.post("/api/v1/medical-exams", json=sample_medical_exam_data)

    response = client.get(f"/api/v1/medical-exams/user/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_import_medical_exam_from_json(client, db):
    """测试从JSON导入体检数据"""
    user_id, headers = _create_admin_and_user(db, client)

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
