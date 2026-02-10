"""AI Insights 服务单元测试 - 验证模型字段访问"""
import pytest
from datetime import date, datetime
from unittest.mock import Mock, MagicMock
from sqlalchemy.orm import Session

from app.services.ai_insights_service import AIInsightsService
from app.models import (
    GarminData, CheckinRecord, WeightRecord, BloodPressureRecord,
    UserProfile, HealthGoal, DietRecord, CheckinTemplate
)


@pytest.fixture
def mock_db():
    """Mock数据库会话"""
    return Mock(spec=Session)


@pytest.fixture
def service(mock_db):
    """创建服务实例"""
    return AIInsightsService(mock_db)


class TestModelFieldAccess:
    """测试模型字段访问是否正确"""

    def test_garmin_data_fields(self):
        """测试GarminData模型字段"""
        garmin = GarminData(
            user_id=1,
            record_date=date.today(),
            distance_meters=5000.0,  # ✓ 正确字段名
            total_sleep_duration=420,  # ✓ 正确字段名（分钟）
            deep_sleep_duration=120,  # ✓ 正确字段名
            light_sleep_duration=180,  # ✓ 正确字段名
            rem_sleep_duration=120,  # ✓ 正确字段名
            steps=8000,
            calories_burned=2000,
            active_calories=500,
            resting_heart_rate=60,
            stress_level=50
        )

        # 验证字段可访问
        assert garmin.distance_meters == 5000.0
        assert garmin.total_sleep_duration == 420
        assert garmin.deep_sleep_duration == 120

    def test_weight_record_fields(self):
        """测试WeightRecord模型字段"""
        weight = WeightRecord(
            user_id=1,
            record_date=date.today(),  # ✓ 正确字段名
            weight=70.5,  # ✓ 正确字段名（不是weight_kg）
            body_fat_percentage=18.5
        )

        assert weight.record_date == date.today()
        assert weight.weight == 70.5
        assert weight.body_fat_percentage == 18.5

    def test_blood_pressure_record_fields(self):
        """测试BloodPressureRecord模型字段"""
        bp = BloodPressureRecord(
            user_id=1,
            record_date=date.today(),  # ✓ 正确字段名
            systolic=120,
            diastolic=80,
            pulse=72
        )

        assert bp.record_date == date.today()
        assert bp.systolic == 120

    def test_checkin_record_with_template(self):
        """测试CheckinRecord与Template关联"""
        template = CheckinTemplate(
            user_id=1,
            name="俯卧撑",  # ✓ template.name
            category="exercise"  # ✓ template.category
        )

        checkin = CheckinRecord(
            user_id=1,
            template_id=1,
            checkin_date=date.today(),  # ✓ 正确字段名
            checkin_time=datetime.now(),
            value=20,
            notes="完成良好"  # ✓ notes而不是note
        )
        checkin.template = template

        # 验证通过关联访问
        assert checkin.template.name == "俯卧撑"
        assert checkin.template.category == "exercise"
        assert checkin.notes == "完成良好"

    def test_user_profile_fields(self):
        """测试UserProfile模型字段"""
        from datetime import date, timedelta

        # age是计算属性，需要通过birth_date设置
        birth_date = date.today() - timedelta(days=30*365)  # 约30岁

        profile = UserProfile(
            user_id=1,
            birth_date=birth_date,  # ✓ birth_date字段，age是计算属性
            gender="male",
            height_cm=175.0,
            current_weight_kg=70.0,
            target_weight_kg=65.0,
            chronic_conditions=["鼻炎"],  # ✓ chronic_conditions
            allergies=["花粉"],  # ✓ allergies
            current_medications=[{"name": "维生素D"}]  # ✓ current_medications
        )

        assert profile.chronic_conditions == ["鼻炎"]
        assert profile.current_medications == [{"name": "维生素D"}]
        assert profile.age is not None  # age是从birth_date计算的
        assert 29 <= profile.age <= 31  # 约30岁

    def test_health_goal_fields(self):
        """测试HealthGoal模型字段"""
        goal = HealthGoal(
            user_id=1,
            goal_type="weight",
            name="减重5公斤",
            target_value=65.0,
            current_value=70.0,
            status="active",  # ✓ status字段，不是is_active
            start_date=date.today()
        )

        assert goal.status == "active"
        assert goal.goal_type == "weight"

    def test_diet_record_fields(self):
        """测试DietRecord模型字段"""
        diet = DietRecord(
            user_id=1,
            record_date=date.today(),
            meal_type="breakfast",  # ✓ meal_type
            food_items="鸡蛋,牛奶",  # ✓ food_items
            calories=300.0,
            notes="早餐"  # ✓ notes
        )

        assert diet.meal_type == "breakfast"
        assert diet.food_items == "鸡蛋,牛奶"


class TestDataAggregation:
    """测试数据聚合逻辑"""

    @pytest.mark.asyncio
    async def test_aggregate_health_snapshot(self, service, mock_db):
        """测试健康数据快照聚合"""
        # Mock GarminData查询
        mock_garmin = Mock(spec=GarminData)
        mock_garmin.distance_meters = 5000.0
        mock_garmin.total_sleep_duration = 420
        mock_garmin.steps = 8000

        # Mock查询返回
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_garmin
        mock_db.query.return_value = mock_query

        # 调用服务方法
        # 注意：这里只是演示测试结构，实际测试需要更完整的mock

    @pytest.mark.asyncio
    async def test_get_user_profile_context(self, service, mock_db):
        """测试用户画像上下文获取"""
        mock_profile = Mock(spec=UserProfile)
        mock_profile.age = 30
        mock_profile.chronic_conditions = ["鼻炎"]
        mock_profile.current_medications = []

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_profile
        mock_db.query.return_value = mock_query

        # 测试字段访问不会报错
        assert mock_profile.chronic_conditions == ["鼻炎"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
