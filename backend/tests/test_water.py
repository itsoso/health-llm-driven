"""饮水记录API测试"""
import pytest
from datetime import date, time
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="wateruser",
        email="water@example.com",
        hashed_password="hashed_password",
        name="饮水测试用户",
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
def sample_water_data():
    """示例饮水数据"""
    return {
        "record_date": str(date.today()),
        "amount": 250,
        "drink_type": "water",
        "notes": "早起喝水"
    }


class TestWaterAPI:
    """饮水记录API测试类"""
    
    def test_create_water_record(self, client, auth_headers, sample_water_data):
        """测试创建饮水记录"""
        response = client.post(
            "/api/v1/water/records",
            json=sample_water_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["amount"] == 250
        assert data["drink_type"] == "water"
        assert "id" in data
    
    def test_create_water_record_minimal(self, client, auth_headers):
        """测试创建最小饮水记录"""
        minimal_data = {
            "record_date": str(date.today()),
            "amount": 200
        }
        response = client.post(
            "/api/v1/water/records",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["amount"] == 200
    
    def test_quick_add_water(self, client, auth_headers):
        """测试快速添加饮水"""
        response = client.post(
            "/api/v1/water/records/me/quick?amount=300",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["amount"] == 300
    
    def test_get_my_water_records(self, client, auth_headers, sample_water_data):
        """测试获取我的饮水记录"""
        # 先创建记录
        client.post(
            "/api/v1/water/records",
            json=sample_water_data,
            headers=auth_headers
        )
        
        # 获取记录
        response = client.get(
            "/api/v1/water/records/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    def test_get_my_daily_summary(self, client, auth_headers, sample_water_data):
        """测试获取我的每日饮水汇总"""
        # 创建多条记录
        client.post("/api/v1/water/records", json=sample_water_data, headers=auth_headers)
        client.post("/api/v1/water/records/me/quick?amount=300", headers=auth_headers)
        
        # 获取汇总
        today = str(date.today())
        response = client.get(
            f"/api/v1/water/records/me/date/{today}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["record_date"] == today
        assert data["total_amount"] >= 550  # 250 + 300
        assert data["records_count"] >= 2
    
    def test_get_my_water_stats(self, client, auth_headers, sample_water_data):
        """测试获取我的饮水统计"""
        # 先创建记录
        client.post(
            "/api/v1/water/records",
            json=sample_water_data,
            headers=auth_headers
        )
        
        # 获取统计
        response = client.get(
            "/api/v1/water/records/me/stats?days=7",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] >= 1
        assert data["days_recorded"] >= 1
    
    def test_delete_water_record(self, client, auth_headers, sample_water_data):
        """测试删除饮水记录"""
        # 先创建记录
        create_response = client.post(
            "/api/v1/water/records",
            json=sample_water_data,
            headers=auth_headers
        )
        record_id = create_response.json()["id"]
        
        # 删除记录
        delete_response = client.delete(
            f"/api/v1/water/records/{record_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200
    
    def test_unauthorized_access(self, client, sample_water_data):
        """测试未授权访问"""
        response = client.post(
            "/api/v1/water/records",
            json=sample_water_data
        )
        assert response.status_code == 401


class TestWaterValidation:
    """饮水记录验证测试"""
    
    def test_zero_amount(self, client, auth_headers):
        """测试零量饮水"""
        data = {
            "record_date": str(date.today()),
            "amount": 0
        }
        response = client.post(
            "/api/v1/water/records",
            json=data,
            headers=auth_headers
        )
        # 根据业务需求可能允许或不允许
        assert response.status_code in [200, 422]
    
    def test_drink_types(self, client, auth_headers):
        """测试不同饮品类型"""
        drink_types = ["water", "tea", "coffee", "juice", "milk", "other"]
        
        for drink_type in drink_types:
            data = {
                "record_date": str(date.today()),
                "amount": 200,
                "drink_type": drink_type
            }
            response = client.post(
                "/api/v1/water/records",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200, f"饮品类型 {drink_type} 创建失败"

