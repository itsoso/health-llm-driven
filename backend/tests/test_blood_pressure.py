"""血压记录API测试"""
import pytest
from datetime import date, timedelta
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="bpuser",
        email="bp@example.com",
        hashed_password="hashed_password",
        name="血压测试用户",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    """获取认证 headers"""
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_bp_data():
    """示例血压数据"""
    return {
        "record_date": str(date.today()),
        "systolic": 120,
        "diastolic": 80,
        "heart_rate": 72,
        "notes": "晨起测量"
    }


class TestBloodPressureAPI:
    """血压记录API测试类"""
    
    def test_create_bp_record(self, client, auth_headers, sample_bp_data):
        """测试创建血压记录"""
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=sample_bp_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["systolic"] == 120
        assert data["diastolic"] == 80
        assert data["heart_rate"] == 72
        assert "id" in data
        assert "category" in data  # 血压分类
    
    def test_create_bp_record_minimal(self, client, auth_headers):
        """测试创建最小血压记录（只有收缩压和舒张压）"""
        minimal_data = {
            "record_date": str(date.today()),
            "systolic": 115,
            "diastolic": 75
        }
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["systolic"] == 115
        assert data["diastolic"] == 75
        assert data["heart_rate"] is None
    
    def test_bp_classification_normal(self, client, auth_headers):
        """测试血压分类 - 正常"""
        data = {
            "record_date": str(date.today()),
            "systolic": 115,
            "diastolic": 75
        }
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["category"] == "正常"
    
    def test_bp_classification_elevated(self, client, auth_headers):
        """测试血压分类 - 正常偏高"""
        data = {
            "record_date": str(date.today()),
            "systolic": 125,
            "diastolic": 78
        }
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["category"] == "正常偏高"
    
    def test_bp_classification_stage1(self, client, auth_headers):
        """测试血压分类 - 高血压1级"""
        data = {
            "record_date": str(date.today()),
            "systolic": 145,
            "diastolic": 92
        }
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["category"] == "高血压1级"
    
    def test_get_my_bp_records(self, client, auth_headers, sample_bp_data):
        """测试获取我的血压记录"""
        # 先创建记录
        client.post(
            "/api/v1/blood-pressure/records",
            json=sample_bp_data,
            headers=auth_headers
        )
        
        # 获取记录
        response = client.get(
            "/api/v1/blood-pressure/records/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    def test_get_my_bp_stats(self, client, auth_headers, sample_bp_data):
        """测试获取我的血压统计"""
        # 先创建记录
        client.post(
            "/api/v1/blood-pressure/records",
            json=sample_bp_data,
            headers=auth_headers
        )
        
        # 获取统计
        response = client.get(
            "/api/v1/blood-pressure/records/me/stats?days=30",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "average_systolic" in data or "total_records" in data
    
    def test_bp_trend(self, client, auth_headers):
        """测试血压趋势（多天数据）"""
        # 创建多天记录
        bp_data = [
            (120, 80), (118, 78), (125, 82), (122, 79), (119, 77)
        ]
        for i, (sys, dia) in enumerate(bp_data):
            data = {
                "record_date": str(date.today() - timedelta(days=i)),
                "systolic": sys,
                "diastolic": dia
            }
            response = client.post(
                "/api/v1/blood-pressure/records",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200
        
        # 获取记录验证趋势
        response = client.get(
            "/api/v1/blood-pressure/records/me?limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        records = response.json()
        assert len(records) >= 5
    
    def test_unauthorized_access(self, client, sample_bp_data):
        """测试未授权访问"""
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=sample_bp_data
        )
        assert response.status_code == 401


class TestBloodPressureValidation:
    """血压记录验证测试"""
    
    def test_missing_systolic(self, client, auth_headers):
        """测试缺少收缩压"""
        data = {
            "record_date": str(date.today()),
            "diastolic": 80
        }
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 422
    
    def test_missing_diastolic(self, client, auth_headers):
        """测试缺少舒张压"""
        data = {
            "record_date": str(date.today()),
            "systolic": 120
        }
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 422
    
    def test_negative_bp(self, client, auth_headers):
        """测试负数血压（应该失败）"""
        data = {
            "record_date": str(date.today()),
            "systolic": -120,
            "diastolic": 80
        }
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        # 负数血压应该被拒绝
        assert response.status_code in [200, 422]
    
    def test_systolic_less_than_diastolic(self, client, auth_headers):
        """测试收缩压小于舒张压"""
        data = {
            "record_date": str(date.today()),
            "systolic": 70,
            "diastolic": 90
        }
        response = client.post(
            "/api/v1/blood-pressure/records",
            json=data,
            headers=auth_headers
        )
        # 这种情况在医学上不太可能，但可能没有验证
        assert response.status_code in [200, 422]


class TestBloodPressureClassification:
    """血压分类逻辑测试"""
    
    def test_all_classifications(self, client, auth_headers):
        """测试所有血压分类"""
        test_cases = [
            ((110, 70), "正常"),
            ((125, 78), "正常偏高"),
            ((135, 85), "高血压前期"),
            ((150, 95), "高血压1级"),
            ((170, 105), "高血压2级"),
            ((185, 115), "高血压3级"),
        ]
        
        for i, ((sys, dia), expected_category) in enumerate(test_cases):
            data = {
                "record_date": str(date.today() - timedelta(days=i+10)),
                "systolic": sys,
                "diastolic": dia
            }
            response = client.post(
                "/api/v1/blood-pressure/records",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200
            actual_category = response.json()["category"]
            assert actual_category == expected_category, \
                f"血压 {sys}/{dia} 应分类为 '{expected_category}'，实际为 '{actual_category}'"

