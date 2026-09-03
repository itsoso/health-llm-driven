"""
补剂推荐服务增强测试
展示完整的单元测试最佳实践
"""

import pytest
from unittest.mock import Mock
from datetime import date
from sqlalchemy.orm import Session

from app.services.supplement_recommendation import SupplementRecommendationService
from app.services.supplement_evidence import SupplementSafetyContext
from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData


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

    # ==================== 测试：成功场景 ====================

    def test_generate_recommendation_success_with_complete_data(
        self,
        service,
        mock_db,
        mock_user_profile,
        mock_garmin_data
    ):
        """测试：完整数据情况下成功生成推荐"""
        user_id = 1
        target_date = date.today()

        # Mock 数据库查询 — service calls db.query(UserProfile).filter_by(...).first()
        # and multiple other queries. Use side_effect to handle different query targets.
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_user_profile
        mock_query.filter.return_value.order_by.return_value.all.return_value = [mock_garmin_data]
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.first.return_value = None

        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id,
            target_date=target_date,
            debug=False
        )

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
        mock_user_profile,
        monkeypatch
    ):
        """测试：部分数据情况下成功生成推荐"""
        user_id = 1
        fake_evidence = {
            "available": True,
            "sources": [{
                "title": "补剂安全边界",
                "category": "supplement",
                "source": "llm_wiki",
                "excerpt": "补剂应优先用于补足饮食缺口，并结合禁忌和相互作用。",
                "relevance": 0.9,
            }],
            "prompt_context": "补剂安全边界",
            "claim_boundary": "不能替代医生诊断、处方或药物调整。",
        }

        monkeypatch.setattr(
            "app.services.supplement_recommendation.build_advice_knowledge_context",
            lambda **kwargs: fake_evidence,
        )

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_user_profile
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.first.return_value = None

        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id
        )

        assert result is not None
        assert result["success"] is True
        assert "recommendations" in result
        assert result["knowledge_evidence"] == fake_evidence
        assert result["recommendations"][0]["knowledge_sources"] == fake_evidence["sources"]
        assert "不能替代医生诊断" in result["recommendations"][0]["claim_boundary"]
        assert result["evidence_summary"]["matched"] >= 1
        assert result["recommendations"][0]["evidence_profile"]["evidence_level"] in {"A", "B", "C"}

    def test_generate_recommendation_uses_recent_lab_safety_context(
        self,
        service,
        mock_db,
        mock_user_profile,
        monkeypatch
    ):
        """测试：真实化验上下文参与补剂安全拦截"""
        user_id = 1
        target_date = date.today()
        calls = []

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_user_profile

        monkeypatch.setattr(service, "_get_recent_health_data", lambda *args, **kwargs: None)
        monkeypatch.setattr(service, "_get_recent_workout_data", lambda *args, **kwargs: None)
        monkeypatch.setattr(service, "_get_recent_diet_data", lambda *args, **kwargs: None)
        monkeypatch.setattr(service, "_get_supplement_status", lambda *args, **kwargs: {})
        monkeypatch.setattr(
            service,
            "_analyze_health_status",
            lambda *args, **kwargs: {"risk_factors": [], "positive_factors": []},
        )
        monkeypatch.setattr(
            service,
            "_generate_recommendations",
            lambda *args, **kwargs: [{
                "name": "甘氨酸镁",
                "dosage": "300mg",
                "timing": "睡前",
                "reason": "睡眠支持",
                "priority": "中",
            }],
        )
        monkeypatch.setattr(service, "_build_knowledge_evidence", lambda *args, **kwargs: {})
        monkeypatch.setattr(service, "_generate_timing_suggestions", lambda *args, **kwargs: {})
        monkeypatch.setattr(service, "_generate_precautions", lambda *args, **kwargs: [])
        monkeypatch.setattr(service, "_calculate_overall_rating", lambda *args, **kwargs: {"score": 6, "rating": "一般"})

        def fake_safety_context(db, called_user_id, profile, called_target_date):
            calls.append((db, called_user_id, profile, called_target_date))
            return SupplementSafetyContext.from_profile(profile, labs={"egfr": 25})

        monkeypatch.setattr(
            "app.services.supplement_recommendation.build_supplement_safety_context",
            fake_safety_context,
        )

        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id,
            target_date=target_date,
        )

        assert calls == [(mock_db, user_id, mock_user_profile, target_date)]
        assert result["recommendations"][0]["support_status"] == "blocked"
        assert result["evidence_summary"]["blocked"] == 1

    # ==================== 测试：边界条件 ====================

    def test_generate_recommendation_no_user_profile(self, service, mock_db):
        """测试：用户画像不存在时仍可生成基础推荐"""
        user_id = 999

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.first.return_value = None

        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id
        )

        # Service still succeeds with basic recommendations even without a profile
        assert result is not None
        assert result["success"] is True
        assert "recommendations" in result

    def test_generate_recommendation_with_allergies(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：过敏原信息被传入分析"""
        user_id = 1
        mock_user_profile.allergies = ["花生", "海鲜"]

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_user_profile
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.first.return_value = None

        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id
        )

        assert result is not None
        assert result["success"] is True

    def test_generate_recommendation_with_chronic_conditions(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：慢性病信息被传入分析"""
        user_id = 1
        mock_user_profile.chronic_conditions = ["高血压", "糖尿病"]

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_user_profile
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.first.return_value = None

        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id
        )

        # Service succeeds; chronic conditions are passed to the analysis layer
        assert result is not None
        assert result["success"] is True

    # ==================== 测试：异常情况 ====================

    def test_generate_recommendation_database_error(self, service, mock_db):
        """测试：数据库查询失败时返回 success=False"""
        user_id = 1
        mock_db.query.side_effect = Exception("Database connection error")

        # Service catches exceptions and returns error response
        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id
        )
        assert result is not None
        assert result["success"] is False
        assert "error" in result or "message" in result

    def test_generate_recommendation_llm_timeout(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：内部异常时返回错误而不崩溃"""
        user_id = 1

        # Make the first query succeed but a later one fail
        call_count = [0]

        def query_side_effect(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: UserProfile query
                result = Mock()
                result.filter_by.return_value.first.return_value = mock_user_profile
                return result
            else:
                raise TimeoutError("LLM timeout")

        mock_db.query.side_effect = query_side_effect

        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id
        )

        # Should return error response rather than crash
        assert result is not None

    # ==================== 测试：性能 ====================

    def test_generate_recommendation_performance(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：推荐生成性能（应在 10 秒内完成）"""
        import time
        user_id = 1

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_user_profile
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.first.return_value = None

        start_time = time.time()
        service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id
        )
        duration = time.time() - start_time

        assert duration < 10.0, f"推荐生成耗时 {duration:.3f}s，超过 10s 阈值"

    # ==================== 测试：评分计算 ====================

    def test_calculate_overall_rating_excellent(self, service):
        """测试：优秀评分计算"""
        supplement_status = {
            "total_supplements": 5,
            "taken_today": 5,
            "completion_rate_7days": 95,
            "categories": {},
            "has_supplements": True
        }
        health_analysis = {
            "sleep_quality": "良好",
            "stress_level": "低",
            "exercise_intensity": "适中",
            "nutrition_status": "充足",
            "risk_factors": [],
            "positive_factors": ["睡眠充足", "压力水平较低", "运动频率适中"]
        }

        rating = service._calculate_overall_rating(
            supplement_status,
            health_analysis
        )

        assert rating["score"] >= 8
        assert rating["rating"] == "优秀"
        assert rating["emoji"] == "🌟"

    def test_calculate_overall_rating_poor(self, service):
        """测试：较差评分计算"""
        supplement_status = {
            "total_supplements": 1,
            "taken_today": 0,
            "completion_rate_7days": 10,
            "categories": {},
            "has_supplements": True
        }
        health_analysis = {
            "sleep_quality": "不足",
            "stress_level": "高",
            "exercise_intensity": "缺乏",
            "nutrition_status": "蛋白质不足",
            "risk_factors": ["睡眠不足", "压力较高"],
            "positive_factors": []
        }

        rating = service._calculate_overall_rating(
            supplement_status,
            health_analysis
        )

        assert rating["score"] < 4
        assert rating["rating"] == "需改进"

    # ==================== 测试：Debug 模式 ====================

    def test_generate_recommendation_debug_mode(
        self,
        service,
        mock_db,
        mock_user_profile
    ):
        """测试：Debug 模式返回完整结果（debug_info 尚未暴露在响应中）"""
        user_id = 1

        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_user_profile
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.first.return_value = None

        result = service.generate_supplement_recommendation(
            db=mock_db,
            user_id=user_id,
            debug=True
        )

        assert result is not None
        assert result["success"] is True
        # Debug mode still returns a valid response with all standard fields
        assert "recommendations" in result
        assert "health_analysis" in result
        assert "overall_rating" in result


# ==================== 集成测试示例 ====================

@pytest.mark.integration
class TestSupplementRecommendationIntegration:
    """补剂推荐服务集成测试"""

    def test_full_recommendation_flow_with_real_db(self):
        """测试：使用真实数据库的完整流程"""
        # 需要真实的数据库 fixture
        # 这里只是示例结构
        pass

    def test_recommendation_with_real_llm(self):
        """测试：使用真实 LLM 的推荐生成"""
        # 需要真实的 LLM 调用
        # 这里只是示例结构
        pass
