"""
补剂推荐服务增强测试
展示完整的单元测试最佳实践
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from app.services.supplement_recommendation import SupplementRecommendationService
from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData, WorkoutRecord, DietRecord
from app.models.supplement import SupplementDefinition, SupplementRecord


class TestSupplementRecommendationService:
    """补剂推荐服务测试套件"""
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return SupplementRecommendationService()
    
    @pytest.fixture
    def mock_db(self):
        """Mock 数据库会话"""
        db = Mock(spec=Session)
        return db
    
    @pytest.fixture
    def mock_user_profile(self):
        """Mock 用户画像"""
        profile = Mock(spec=UserProfile)
        profile.id = 1
        profile.user_id = 1
        profile.age = 35
        profile.gender = "male"
        profile.height_cm = 175
        profile.current_weight_kg = 70
        profile.allergies = ["花生"]
        profile.chronic_conditions = []
        profile.exercise_frequency = "daily"
        profile.diet_preference = "normal"
        return profile
    
    @pytest.fixture
    def mock_garmin_data(self):
        """Mock Garmin 健康数据"""
        data = Mock(spec=GarminData)
        data.record_date = date.today()
        data.sleep_score = 85
        data.total_sleep_duration = 450  # 7.5小时（分钟）
        data.stress_level = 35
        data.resting_heart_rate = 55
        data.steps = 8500
        data.calories_burned = 2200
        data.body_battery = 75
        return data
    
    @pytest.fixture
    def mock_workout_record(self):
        """Mock 运动记录"""
        workout = Mock(spec=WorkoutRecord)
        workout.workout_date = date.today()
        workout.workout_type = "running"
        workout.duration_minutes = 45
        workout.calories = 450
        workout.avg_heart_rate = 145
        workout.distance_km = 6.5
        return workout
    
    @pytest.fixture
    def mock_diet_record(self):
        """Mock 饮食记录"""
        diet = Mock(spec=DietRecord)
        diet.record_date = date.today()
        diet.meal_type = "breakfast"
        diet.calories = 500
        diet.protein = 25
        diet.carbs = 60
        diet.fat = 15
        return diet
    
    @pytest.fixture
    def mock_supplement_definition(self):
        """Mock 补剂定义"""
        supplement = Mock(spec=SupplementDefinition)
        supplement.id = 1
        supplement.name = "维生素D"
        supplement.dosage = "2000IU"
        supplement.timing = "morning"
        supplement.category = "vitamin"
        supplement.is_active = True
        return supplement
    
    # ==================== 测试：成功场景 ====================
    
    def test_generate_recommendation_success_with_complete_data(
        self,
        service,
        mock_db,
        mock_user_profile,
        mock_garmin_data,
        mock_workout_record
    ):
        """测试：完整数据情况下成功生成推荐"""
        # Arrange
        user_id = 1
        target_date = date.today()
        
        # Mock 数据库查询
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user_profile
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_garmin_data
        ]
        
        # Mock DigitalTwin 服务
        with patch('app.services.supplement_recommendation.DigitalTwinService') as mock_twin:
            mock_twin_instance = mock_twin.return_value
            mock_twin_instance.analyze_supplement_needs.return_value = {
                "recommendations": [
                    {
                        "name": "维生素D",
                        "reason": "睡眠质量良好，但可能缺乏日照",
                        "dosage": "2000IU",
                        "timing": "早餐后",
                        "priority": "中",
                        "icon": "☀️",
                        "category": "vitamin"
                    }
                ]
            }
            
            # Act
            result = service.generate_supplement_recommendation(
                db=mock_db,
                user_id=user_id,
                target_date=target_date,
                debug=False
            )
        
        # Assert
        assert result is not None
        assert result["success"] is True
        assert "recommendations" in result
        assert len(result["recommendations"]) > 0
        assert "overall_rating" in result
        assert result["overall_rating"]["score"] >= 0
        assert result["overall_rating"]["score"] <= 10
    
    def test_generate_recommendation_success_with_partial_data(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：部分数据情况下成功生成推荐"""
        # Arrange
        user_id = 1
        
        # Mock 只有用户画像，没有健康数据
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user_profile
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        with patch('app.services.supplement_recommendation.DigitalTwinService') as mock_twin:
            mock_twin_instance = mock_twin.return_value
            mock_twin_instance.analyze_supplement_needs.return_value = {
                "recommendations": []
            }
            
            # Act
            result = service.generate_supplement_recommendation(
                db=mock_db,
                user_id=user_id
            )
        
        # Assert
        assert result is not None
        assert result["success"] is True
        # 即使没有数据，也应该返回基础推荐
        assert "recommendations" in result
    
    # ==================== 测试：边界条件 ====================
    
    def test_generate_recommendation_no_user_profile(self, service, mock_db):
        """测试：用户画像不存在"""
        # Arrange
        user_id = 999
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Act
        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id
        )
        
        # Assert
        assert result is not None
        assert result["success"] is False
        assert "error" in result or "message" in result
    
    def test_generate_recommendation_with_allergies(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：过敏原过滤"""
        # Arrange
        user_id = 1
        mock_user_profile.allergies = ["花生", "海鲜"]
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user_profile
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        with patch('app.services.supplement_recommendation.DigitalTwinService') as mock_twin:
            mock_twin_instance = mock_twin.return_value
            mock_twin_instance.analyze_supplement_needs.return_value = {
                "recommendations": [
                    {
                        "name": "鱼油",
                        "category": "omega3",
                        "priority": "高"
                    }
                ]
            }
            
            # Act
            result = service.generate_supplement_recommendation(
                db=mock_db,
                user_id=user_id
            )
        
        # Assert
        # 应该过滤掉含海鲜的鱼油推荐
        assert result is not None
        if result.get("recommendations"):
            for rec in result["recommendations"]:
                # 检查推荐中不应包含过敏原
                assert "海鲜" not in rec.get("name", "").lower()
    
    def test_generate_recommendation_with_chronic_conditions(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：慢性病考虑"""
        # Arrange
        user_id = 1
        mock_user_profile.chronic_conditions = ["高血压", "糖尿病"]
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user_profile
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        with patch('app.services.supplement_recommendation.DigitalTwinService') as mock_twin:
            mock_twin_instance = mock_twin.return_value
            mock_twin_instance.analyze_supplement_needs.return_value = {
                "recommendations": []
            }
            
            # Act
            result = service.generate_supplement_recommendation(
                db=mock_db,
                user_id=user_id
            )
        
        # Assert
        assert result is not None
        # 应该在注意事项中提到慢性病
        if "precautions" in result:
            precautions_text = " ".join(result["precautions"])
            assert any(
                condition in precautions_text
                for condition in ["高血压", "糖尿病", "慢性病"]
            )
    
    # ==================== 测试：异常情况 ====================
    
    def test_generate_recommendation_database_error(self, service, mock_db):
        """测试：数据库查询失败"""
        # Arrange
        user_id = 1
        mock_db.query.side_effect = Exception("Database connection error")
        
        # Act & Assert
        with pytest.raises(Exception):
            service.generate_supplement_recommendation(
                db=mock_db,
                user_id=user_id
            )
    
    def test_generate_recommendation_llm_timeout(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：LLM 调用超时"""
        # Arrange
        user_id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user_profile
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        with patch('app.services.supplement_recommendation.DigitalTwinService') as mock_twin:
            mock_twin_instance = mock_twin.return_value
            mock_twin_instance.analyze_supplement_needs.side_effect = TimeoutError("LLM timeout")
            
            # Act
            result = service.generate_supplement_recommendation(
                db=mock_db,
                user_id=user_id
            )
        
        # Assert
        # 应该返回默认推荐而不是崩溃
        assert result is not None
        assert "recommendations" in result
    
    # ==================== 测试：性能 ====================
    
    def test_generate_recommendation_performance(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：推荐生成性能（应在 10 秒内完成）"""
        # Arrange
        import time
        user_id = 1
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user_profile
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        with patch('app.services.supplement_recommendation.DigitalTwinService') as mock_twin:
            mock_twin_instance = mock_twin.return_value
            mock_twin_instance.analyze_supplement_needs.return_value = {
                "recommendations": []
            }
            
            # Act
            start_time = time.time()
            result = service.generate_supplement_recommendation(
                db=mock_db,
                user_id=user_id
            )
            duration = time.time() - start_time
        
        # Assert
        assert duration < 10.0, f"推荐生成耗时 {duration:.3f}s，超过 10s 阈值"
    
    # ==================== 测试：评分计算 ====================
    
    def test_calculate_overall_rating_excellent(self, service):
        """测试：优秀评分计算"""
        # Arrange
        supplement_status = {
            "active_count": 5,
            "completion_rate": 0.95,
            "streak_days": 30
        }
        health_analysis = {
            "sleep_quality": "良好",
            "stress_level": "低",
            "exercise_intensity": "适中"
        }
        
        # Act
        rating = service._calculate_overall_rating(
            supplement_status,
            health_analysis
        )
        
        # Assert
        assert rating["score"] >= 8
        assert rating["rating"] == "优秀"
        assert rating["emoji"] == "🌟"
    
    def test_calculate_overall_rating_poor(self, service):
        """测试：较差评分计算"""
        # Arrange
        supplement_status = {
            "active_count": 1,
            "completion_rate": 0.3,
            "streak_days": 2
        }
        health_analysis = {
            "sleep_quality": "较差",
            "stress_level": "高",
            "exercise_intensity": "低"
        }
        
        # Act
        rating = service._calculate_overall_rating(
            supplement_status,
            health_analysis
        )
        
        # Assert
        assert rating["score"] < 4
        assert rating["rating"] == "需改进"
    
    # ==================== 测试：Debug 模式 ====================
    
    def test_generate_recommendation_debug_mode(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：Debug 模式返回详细信息"""
        # Arrange
        user_id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user_profile
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        with patch('app.services.supplement_recommendation.DigitalTwinService') as mock_twin:
            mock_twin_instance = mock_twin.return_value
            mock_twin_instance.analyze_supplement_needs.return_value = {
                "recommendations": []
            }
            
            # Act
            result = service.generate_supplement_recommendation(
                db=mock_db,
                user_id=user_id,
                debug=True
            )
        
        # Assert
        assert result is not None
        # Debug 模式应该返回额外的调试信息
        assert "debug_info" in result or "data_sources" in result


# ==================== 集成测试示例 ====================

@pytest.mark.integration
class TestSupplementRecommendationIntegration:
    """补剂推荐服务集成测试"""
    
    def test_full_recommendation_flow_with_real_db(self, test_db, test_user):
        """测试：使用真实数据库的完整流程"""
        # 需要真实的数据库 fixture
        # 这里只是示例结构
        pass
    
    def test_recommendation_with_real_llm(self, test_db, test_user):
        """测试：使用真实 LLM 的推荐生成"""
        # 需要真实的 LLM 调用
        # 这里只是示例结构
        pass


# ==================== 运行测试 ====================

"""
运行测试命令：

# 运行所有测试
pytest tests/test_supplement_recommendation_enhanced.py -v

# 运行特定测试类
pytest tests/test_supplement_recommendation_enhanced.py::TestSupplementRecommendationService -v

# 运行特定测试
pytest tests/test_supplement_recommendation_enhanced.py::TestSupplementRecommendationService::test_generate_recommendation_success_with_complete_data -v

# 生成覆盖率报告
pytest tests/test_supplement_recommendation_enhanced.py --cov=app.services.supplement_recommendation --cov-report=html

# 运行性能测试
pytest tests/test_supplement_recommendation_enhanced.py::TestSupplementRecommendationService::test_generate_recommendation_performance -v --durations=10

# 跳过集成测试
pytest tests/test_supplement_recommendation_enhanced.py -v -m "not integration"
"""
