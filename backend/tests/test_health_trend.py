"""健康趋势预测服务测试"""
import pytest
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.health_trend import HealthTrendReport
from app.models.daily_health import GarminData
from app.models.weight import WeightRecord
from app.models.user import User
from app.services.health_trend_service import HealthTrendService


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(name="趋势测试用户", phone="13900139000")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def service(db):
    """创建服务实例"""
    return HealthTrendService(db)


@pytest.fixture
def today():
    return date(2026, 3, 4)


def _create_garmin_data(db, user_id, record_date, **kwargs):
    """辅助函数：创建Garmin数据"""
    data = GarminData(user_id=user_id, record_date=record_date, **kwargs)
    db.add(data)
    db.commit()
    return data


def _create_weight_record(db, user_id, record_date, weight, bmi=None):
    """辅助函数：创建体重记录"""
    record = WeightRecord(user_id=user_id, record_date=record_date, weight=weight, bmi=bmi)
    db.add(record)
    db.commit()
    return record


class TestAggregateWeightData:
    """体重数据聚合测试"""

    def test_aggregate_weight_7d_with_data(self, db, test_user, service, today):
        """7天内有体重数据时应正确聚合"""
        for i in range(7):
            d = today - timedelta(days=i)
            _create_weight_record(db, test_user.id, d, weight=70.0 + i * 0.1)

        data = service._aggregate_weight_data(test_user.id, today, days=7)
        assert data is not None
        assert len(data["records"]) == 7
        assert "latest" in data
        assert "earliest" in data
        assert "change" in data

    def test_aggregate_weight_no_data(self, db, test_user, service, today):
        """没有体重数据时应返回None"""
        data = service._aggregate_weight_data(test_user.id, today, days=7)
        assert data is None


class TestAggregateSleepData:
    """睡眠数据聚合测试"""

    def test_aggregate_sleep_with_data(self, db, test_user, service, today):
        """有睡眠数据时应正确聚合"""
        for i in range(7):
            d = today - timedelta(days=i)
            _create_garmin_data(db, test_user.id, d,
                                sleep_score=75 + i, total_sleep_duration=420 + i * 10,
                                deep_sleep_duration=60 + i)

        data = service._aggregate_sleep_data(test_user.id, today, days=7)
        assert data is not None
        assert "avg_sleep_score" in data
        assert "avg_total_duration" in data
        assert "avg_deep_sleep" in data
        assert len(data["daily"]) == 7

    def test_aggregate_sleep_no_data(self, db, test_user, service, today):
        """没有睡眠数据时应返回None"""
        data = service._aggregate_sleep_data(test_user.id, today, days=7)
        assert data is None


class TestAggregateExerciseData:
    """运动数据聚合测试"""

    def test_aggregate_exercise_with_data(self, db, test_user, service, today):
        """有运动数据时应正确聚合"""
        for i in range(7):
            d = today - timedelta(days=i)
            _create_garmin_data(db, test_user.id, d,
                                steps=8000 + i * 500, calories_burned=2000 + i * 100,
                                active_minutes=30 + i * 5)

        data = service._aggregate_exercise_data(test_user.id, today, days=7)
        assert data is not None
        assert "avg_steps" in data
        assert "avg_calories" in data
        assert "total_active_minutes" in data

    def test_aggregate_exercise_no_data(self, db, test_user, service, today):
        """没有运动数据时应返回None"""
        data = service._aggregate_exercise_data(test_user.id, today, days=7)
        assert data is None


class TestBuildPrompt:
    """Prompt 构建测试"""

    def test_build_prompt_weight(self, service):
        """体重维度 prompt 应包含关键信息"""
        data = {
            "records": [{"date": "2026-03-01", "weight": 70.0}],
            "latest": 70.0,
            "earliest": 71.0,
            "change": -1.0,
        }
        prompt = service._build_dimension_prompt("weight", data)
        assert "体重" in prompt
        assert "70.0" in prompt
        assert "趋势" in prompt

    def test_build_prompt_sleep(self, service):
        """睡眠维度 prompt 应包含关键信息"""
        data = {
            "avg_sleep_score": 78,
            "avg_total_duration": 440,
            "avg_deep_sleep": 65,
            "daily": [{"date": "2026-03-01", "sleep_score": 78}],
        }
        prompt = service._build_dimension_prompt("sleep", data)
        assert "睡眠" in prompt
        assert "78" in prompt


class TestParseAnalysisResult:
    """分析结果解析测试"""

    def test_parse_valid_result(self, service):
        """应正确解析 OpenClaw 返回的结果"""
        raw = {
            "status": "completed",
            "aggregation": """趋势方向：improving
洞察：
1. 体重在过去7天持续下降
2. 平均每天减少0.15kg
建议：
1. 保持当前饮食计划
2. 增加力量训练
风险：无""",
            "model_results": [{"model": "gpt-4", "text": "..."}],
        }
        parsed = service._parse_analysis_result(raw)
        assert parsed["trend_direction"] in ("improving", "declining", "stable")
        assert len(parsed["insights"]) > 0
        assert len(parsed["suggestions"]) > 0

    def test_parse_empty_result(self, service):
        """空结果应返回默认值"""
        raw = {"status": "error", "aggregation": "", "model_results": []}
        parsed = service._parse_analysis_result(raw)
        assert parsed["trend_direction"] == "stable"
        assert parsed["insights"] == []


class TestStoreReport:
    """报告存储测试"""

    def test_store_report_creates_record(self, db, test_user, service, today):
        """应正确创建报告记录"""
        service._store_report(
            user_id=test_user.id,
            report_date=today,
            dimension="weight",
            period="7d",
            trend_direction="improving",
            raw_data_summary={"latest": 70.0},
            insights=["体重持续下降"],
            suggestions=["保持饮食计划"],
            risk_alerts=[],
            full_report="完整报告内容",
            openclaw_batch_id="batch-123",
            model_results=[],
        )

        report = db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == test_user.id,
            HealthTrendReport.dimension == "weight",
        ).first()
        assert report is not None
        assert report.trend_direction == "improving"
        assert report.insights == ["体重持续下降"]

    def test_store_report_upsert(self, db, test_user, service, today):
        """同一维度同一天应覆盖更新"""
        service._store_report(
            user_id=test_user.id, report_date=today, dimension="weight", period="7d",
            trend_direction="stable", raw_data_summary={}, insights=["旧洞察"],
            suggestions=[], risk_alerts=[], full_report="旧报告",
            openclaw_batch_id="batch-1", model_results=[],
        )
        service._store_report(
            user_id=test_user.id, report_date=today, dimension="weight", period="7d",
            trend_direction="improving", raw_data_summary={}, insights=["新洞察"],
            suggestions=[], risk_alerts=[], full_report="新报告",
            openclaw_batch_id="batch-2", model_results=[],
        )

        reports = db.query(HealthTrendReport).filter(
            HealthTrendReport.user_id == test_user.id,
            HealthTrendReport.dimension == "weight",
            HealthTrendReport.report_date == today,
        ).all()
        assert len(reports) == 1
        assert reports[0].trend_direction == "improving"
        assert reports[0].insights == ["新洞察"]


class TestGetLatest:
    """获取最新报告测试"""

    def test_get_latest_returns_all_dimensions(self, db, test_user, service, today):
        """应返回所有维度的最新报告"""
        for dim in ["weight", "sleep", "exercise", "overall"]:
            service._store_report(
                user_id=test_user.id, report_date=today, dimension=dim, period="7d",
                trend_direction="stable", raw_data_summary={}, insights=["测试"],
                suggestions=[], risk_alerts=[], full_report="报告",
                openclaw_batch_id="b1", model_results=[],
            )

        result = service.get_latest(test_user.id)
        assert len(result) == 4
        dims = [r.dimension for r in result]
        assert "weight" in dims
        assert "sleep" in dims

    def test_get_latest_empty(self, db, test_user, service):
        """无报告时返回空列表"""
        result = service.get_latest(test_user.id)
        assert result == []
