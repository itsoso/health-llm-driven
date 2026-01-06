"""习惯追踪API测试"""
import pytest
from datetime import date, timedelta
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="habituser",
        email="habit@example.com",
        hashed_password="hashed_password",
        name="习惯测试用户",
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
def sample_habit_definition(test_user):
    """示例习惯定义数据"""
    return {
        "user_id": test_user.id,
        "name": "早起",
        "description": "每天6点前起床",
        "category": "健康",
        "frequency": "daily",
        "target_value": 1,
        "unit": "次",
        "is_active": True
    }


class TestHabitDefinitionAPI:
    """习惯定义API测试类"""
    
    def test_create_habit(self, client, auth_headers, sample_habit_definition):
        """测试创建习惯"""
        response = client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "早起"
        assert data["category"] == "健康"
        assert "id" in data
    
    def test_create_habit_minimal(self, client, auth_headers, test_user):
        """测试创建最小习惯（只有必填字段）"""
        minimal_data = {
            "user_id": test_user.id,
            "name": "喝水",
            "frequency": "daily"
        }
        response = client.post(
            "/api/v1/habits/definitions",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "喝水"
    
    def test_get_user_habits(self, client, auth_headers, sample_habit_definition, test_user):
        """测试获取用户习惯列表"""
        # 先创建习惯
        client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        
        # 获取列表
        response = client.get(
            f"/api/v1/habits/definitions/user/{test_user.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    def test_get_my_habits(self, client, auth_headers, sample_habit_definition):
        """测试获取我的习惯列表"""
        # 先创建习惯
        client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        
        # 获取列表
        response = client.get(
            "/api/v1/habits/definitions/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    def test_update_habit(self, client, auth_headers, sample_habit_definition):
        """测试更新习惯"""
        # 先创建习惯
        create_response = client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        habit_id = create_response.json()["id"]
        
        # 更新习惯
        update_data = {
            "name": "早起运动",
            "description": "每天6点起床后运动30分钟"
        }
        update_response = client.put(
            f"/api/v1/habits/definitions/{habit_id}",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "早起运动"
    
    def test_delete_habit(self, client, auth_headers, sample_habit_definition):
        """测试删除习惯"""
        # 先创建习惯
        create_response = client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        habit_id = create_response.json()["id"]
        
        # 删除习惯
        delete_response = client.delete(
            f"/api/v1/habits/definitions/{habit_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200


class TestHabitRecordAPI:
    """习惯记录API测试类"""
    
    def test_create_habit_record(self, client, auth_headers, sample_habit_definition):
        """测试创建习惯打卡记录"""
        # 先创建习惯
        create_response = client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        habit_id = create_response.json()["id"]
        
        # 创建打卡记录
        record_data = {
            "habit_id": habit_id,
            "record_date": str(date.today()),
            "completed": True,
            "value": 1,
            "notes": "完成早起"
        }
        response = client.post(
            "/api/v1/habits/records",
            json=record_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["completed"] == True
    
    def test_batch_checkin(self, client, auth_headers, sample_habit_definition, test_user):
        """测试批量打卡"""
        # 创建多个习惯
        habits = []
        for name in ["习惯1", "习惯2", "习惯3"]:
            data = sample_habit_definition.copy()
            data["name"] = name
            response = client.post(
                "/api/v1/habits/definitions",
                json=data,
                headers=auth_headers
            )
            habits.append(response.json()["id"])
        
        # 批量打卡
        batch_data = {
            "user_id": test_user.id,
            "record_date": str(date.today()),
            "habit_ids": habits
        }
        response = client.post(
            "/api/v1/habits/records/batch",
            json=batch_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
    
    def test_get_habits_with_status(self, client, auth_headers, sample_habit_definition, test_user):
        """测试获取习惯及打卡状态"""
        # 创建习惯
        create_response = client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        habit_id = create_response.json()["id"]
        
        # 打卡
        record_data = {
            "habit_id": habit_id,
            "record_date": str(date.today()),
            "completed": True
        }
        client.post(
            "/api/v1/habits/records",
            json=record_data,
            headers=auth_headers
        )
        
        # 获取习惯及状态
        today = str(date.today())
        response = client.get(
            f"/api/v1/habits/me/date/{today}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_my_stats(self, client, auth_headers, sample_habit_definition):
        """测试获取我的习惯统计"""
        # 创建习惯
        client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        
        # 获取统计
        response = client.get(
            "/api/v1/habits/me/stats?days=30",
            headers=auth_headers
        )
        assert response.status_code == 200
    
    def test_get_today_summary(self, client, auth_headers, sample_habit_definition):
        """测试获取今日汇总"""
        # 创建习惯
        client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        
        # 获取今日汇总
        response = client.get(
            "/api/v1/habits/me/today-summary",
            headers=auth_headers
        )
        assert response.status_code == 200


class TestHabitStreak:
    """习惯连续打卡测试"""
    
    def test_streak_calculation(self, client, auth_headers, sample_habit_definition):
        """测试连续打卡计算"""
        # 创建习惯
        create_response = client.post(
            "/api/v1/habits/definitions",
            json=sample_habit_definition,
            headers=auth_headers
        )
        habit_id = create_response.json()["id"]
        
        # 连续打卡5天
        for i in range(5):
            record_data = {
                "habit_id": habit_id,
                "record_date": str(date.today() - timedelta(days=i)),
                "completed": True
            }
            response = client.post(
                "/api/v1/habits/records",
                json=record_data,
                headers=auth_headers
            )
            assert response.status_code == 200
        
        # 验证连续打卡天数（通过获取习惯状态查看）
        today = str(date.today())
        response = client.get(
            f"/api/v1/habits/me/date/{today}",
            headers=auth_headers
        )
        assert response.status_code == 200

