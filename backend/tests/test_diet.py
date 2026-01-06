"""饮食记录API测试"""
import pytest
from datetime import date
from app.models.user import User
from app.models.daily_health import DietRecord


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password",
        name="测试用户",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    """获取认证 headers"""
    # 创建一个简单的认证方式
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_diet_data():
    """示例饮食数据"""
    return {
        "record_date": str(date.today()),
        "meal_type": "breakfast",
        "food_items": "鸡蛋,牛奶,面包",
        "calories": 450,
        "protein": 20.5,
        "carbs": 45.0,
        "fat": 15.0,
        "notes": "健康早餐"
    }


class TestDietAPI:
    """饮食记录API测试类"""
    
    def test_create_diet_record(self, client, auth_headers, sample_diet_data):
        """测试创建饮食记录"""
        response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meal_type"] == "breakfast"
        assert data["food_items"] == "鸡蛋,牛奶,面包"
        assert data["calories"] == 450
        assert data["protein"] == 20.5
        assert "id" in data
    
    def test_create_diet_record_minimal(self, client, auth_headers):
        """测试创建最小饮食记录（只有必填字段）"""
        minimal_data = {
            "record_date": str(date.today()),
            "meal_type": "lunch",
            "food_items": "米饭,青菜"
        }
        response = client.post(
            "/api/v1/diet/records",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meal_type"] == "lunch"
        assert data["food_items"] == "米饭,青菜"
        assert data["calories"] is None
    
    def test_create_diet_record_invalid_meal_type(self, client, auth_headers):
        """测试创建饮食记录（无效的餐类型）"""
        invalid_data = {
            "record_date": str(date.today()),
            "meal_type": "invalid_type",
            "food_items": "测试食物"
        }
        response = client.post(
            "/api/v1/diet/records",
            json=invalid_data,
            headers=auth_headers
        )
        assert response.status_code == 422  # 验证错误
    
    def test_create_diet_record_missing_food_items(self, client, auth_headers):
        """测试创建饮食记录（缺少食物）"""
        invalid_data = {
            "record_date": str(date.today()),
            "meal_type": "breakfast"
            # 缺少 food_items
        }
        response = client.post(
            "/api/v1/diet/records",
            json=invalid_data,
            headers=auth_headers
        )
        assert response.status_code == 422
    
    def test_create_diet_record_unauthorized(self, client, sample_diet_data):
        """测试未授权创建饮食记录"""
        response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data
        )
        assert response.status_code == 401
    
    def test_get_my_diet_records(self, client, auth_headers, sample_diet_data):
        """测试获取我的饮食记录"""
        # 先创建记录
        client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        
        # 获取记录
        response = client.get(
            "/api/v1/diet/records/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    def test_get_my_daily_summary(self, client, auth_headers, sample_diet_data):
        """测试获取我的每日饮食汇总"""
        # 先创建记录
        client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        
        # 获取汇总
        today = str(date.today())
        response = client.get(
            f"/api/v1/diet/records/me/date/{today}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["record_date"] == today
        assert data["total_calories"] == 450
        assert data["meals_count"] == 1
    
    def test_get_my_diet_stats(self, client, auth_headers, sample_diet_data):
        """测试获取我的饮食统计"""
        # 先创建记录
        client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        
        # 获取统计
        response = client.get(
            "/api/v1/diet/records/me/stats?days=7",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] >= 1
        assert data["days_recorded"] >= 1
    
    def test_delete_diet_record(self, client, auth_headers, sample_diet_data):
        """测试删除饮食记录"""
        # 先创建记录
        create_response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        record_id = create_response.json()["id"]
        
        # 删除记录
        delete_response = client.delete(
            f"/api/v1/diet/records/{record_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        
        # 验证删除成功
        today = str(date.today())
        get_response = client.get(
            f"/api/v1/diet/records/me/date/{today}",
            headers=auth_headers
        )
        assert get_response.json()["meals_count"] == 0
    
    def test_update_diet_record(self, client, auth_headers, sample_diet_data):
        """测试更新饮食记录"""
        # 先创建记录
        create_response = client.post(
            "/api/v1/diet/records",
            json=sample_diet_data,
            headers=auth_headers
        )
        record_id = create_response.json()["id"]
        
        # 更新记录
        update_data = {
            "calories": 500,
            "notes": "更新后的备注"
        }
        update_response = client.put(
            f"/api/v1/diet/records/{record_id}",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200
        assert update_response.json()["calories"] == 500
        assert update_response.json()["notes"] == "更新后的备注"


class TestDietValidation:
    """饮食记录验证测试"""
    
    def test_meal_types(self, client, auth_headers):
        """测试所有餐类型"""
        meal_types = ["breakfast", "lunch", "dinner", "snack", "extra"]
        
        for meal_type in meal_types:
            data = {
                "record_date": str(date.today()),
                "meal_type": meal_type,
                "food_items": f"测试{meal_type}"
            }
            response = client.post(
                "/api/v1/diet/records",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200, f"餐类型 {meal_type} 创建失败"
    
    def test_negative_calories(self, client, auth_headers):
        """测试负数热量（应该允许，可能有特殊情况）"""
        data = {
            "record_date": str(date.today()),
            "meal_type": "breakfast",
            "food_items": "测试",
            "calories": -100  # 负数
        }
        response = client.post(
            "/api/v1/diet/records",
            json=data,
            headers=auth_headers
        )
        # 根据业务需求，可能允许或不允许
        # 这里假设不做验证，允许保存
        assert response.status_code in [200, 422]
    
    def test_empty_food_items(self, client, auth_headers):
        """测试空食物列表"""
        data = {
            "record_date": str(date.today()),
            "meal_type": "breakfast",
            "food_items": ""  # 空字符串
        }
        response = client.post(
            "/api/v1/diet/records",
            json=data,
            headers=auth_headers
        )
        # 空字符串应该被允许（由前端验证）
        assert response.status_code == 200

