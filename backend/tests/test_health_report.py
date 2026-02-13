"""健康报告功能测试 - TDD"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.daily_health import GarminData, DietRecord
from app.models.weight import WeightRecord
from app.models.mood import MoodRecord
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.models.health_report import HealthReport
from app.services.health_report_service import HealthReportService


@pytest.fixture
def report_db():
    """创建测试数据库"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def test_user(report_db):
    """创建测试用户"""
    user = User(
        username="report_test",
        email="report@example.com",
        hashed_password="hashed_password",
        name="报告测试用户",
        is_active=True,
        is_approved=True,
    )
    report_db.add(user)
    report_db.commit()
    report_db.refresh(user)
    return user


@pytest.fixture
def report_service():
    return HealthReportService()


@pytest.fixture
def sample_health_data(report_db, test_user):
    """创建7天的样本健康数据"""
    today = date.today()
    for i in range(7):
        d = today - timedelta(days=i)

        # Garmin 数据
        garmin = GarminData(
            user_id=test_user.id,
            record_date=d,
            steps=8000 + i * 500,
            calories_burned=2000 + i * 100,
            active_calories=400 + i * 50,
            resting_heart_rate=60 + i,
            avg_heart_rate=72 + i,
            hrv=45 + i,
            stress_level=30 + i * 2,
            total_sleep_duration=420 + i * 10,
            deep_sleep_duration=80 + i * 5,
            rem_sleep_duration=90 + i * 3,
            light_sleep_duration=200 + i * 2,
            sleep_score=75 + i,
            body_battery_current=60 + i * 3,
            spo2_avg=97,
        )
        report_db.add(garmin)

        # 饮食记录
        diet = DietRecord(
            user_id=test_user.id,
            record_date=d,
            meal_type="lunch",
            food_items=f"测试食物_{i}",
            calories=600 + i * 50,
            protein=25 + i * 2,
            carbs=80 + i * 5,
            fat=20 + i,
        )
        report_db.add(diet)

        # 体重 (只记录偶数天)
        if i % 2 == 0:
            weight = WeightRecord(
                user_id=test_user.id,
                record_date=d,
                weight=70.0 - i * 0.1,
            )
            report_db.add(weight)

        # 情绪
        mood = MoodRecord(
            user_id=test_user.id,
            record_date=d,
            mood_score=3 + (i % 3),
            mood_tags=["平静"] if i % 2 == 0 else ["开心"],
            energy_level=3 + (i % 3),
            stress_level=2 + (i % 3),
        )
        report_db.add(mood)

    report_db.commit()
    return today


class TestHealthReportModel:
    """测试报告模型"""

    def test_create_report(self, report_db, test_user):
        """测试创建报告"""
        today = date.today()
        report = HealthReport(
            user_id=test_user.id,
            report_type="weekly",
            start_date=today - timedelta(days=6),
            end_date=today,
            title="2026年第7周健康报告",
            exercise_summary={"total_steps": 63000, "avg_daily_steps": 9000},
            health_score=78,
        )
        report_db.add(report)
        report_db.commit()
        report_db.refresh(report)

        assert report.id is not None
        assert report.report_type == "weekly"
        assert report.health_score == 78


class TestHealthReportService:
    """测试报告服务"""

    def test_collect_exercise_data(self, report_db, test_user, report_service, sample_health_data):
        """测试收集运动数据"""
        today = sample_health_data
        start = today - timedelta(days=6)
        summary = report_service._collect_exercise_summary(report_db, test_user.id, start, today)

        assert summary["total_steps"] > 0
        assert summary["avg_daily_steps"] > 0
        assert summary["avg_heart_rate"] is not None

    def test_collect_diet_data(self, report_db, test_user, report_service, sample_health_data):
        """测试收集饮食数据"""
        today = sample_health_data
        start = today - timedelta(days=6)
        summary = report_service._collect_diet_summary(report_db, test_user.id, start, today)

        assert summary["record_days"] > 0
        assert summary["avg_daily_calories"] is not None
        assert summary["avg_daily_calories"] > 0

    def test_collect_sleep_data(self, report_db, test_user, report_service, sample_health_data):
        """测试收集睡眠数据"""
        today = sample_health_data
        start = today - timedelta(days=6)
        summary = report_service._collect_sleep_summary(report_db, test_user.id, start, today)

        assert summary["avg_sleep_duration"] is not None
        assert summary["avg_sleep_score"] is not None

    def test_collect_weight_data(self, report_db, test_user, report_service, sample_health_data):
        """测试收集体重数据"""
        today = sample_health_data
        start = today - timedelta(days=6)
        summary = report_service._collect_weight_summary(report_db, test_user.id, start, today)

        assert summary["record_count"] > 0
        assert summary["start_weight"] is not None
        assert summary["end_weight"] is not None

    def test_collect_mood_data(self, report_db, test_user, report_service, sample_health_data):
        """测试收集情绪数据"""
        today = sample_health_data
        start = today - timedelta(days=6)
        summary = report_service._collect_mood_summary(report_db, test_user.id, start, today)

        assert summary["record_days"] == 7
        assert summary["avg_mood_score"] is not None

    def test_collect_vital_signs(self, report_db, test_user, report_service, sample_health_data):
        """测试收集体征数据"""
        today = sample_health_data
        start = today - timedelta(days=6)
        summary = report_service._collect_vital_signs_summary(report_db, test_user.id, start, today)

        assert summary["avg_resting_heart_rate"] is not None
        assert summary["avg_hrv"] is not None

    def test_generate_weekly_report(self, report_db, test_user, report_service, sample_health_data):
        """测试生成周报"""
        today = sample_health_data
        report = report_service.generate_report(
            db=report_db,
            user_id=test_user.id,
            report_type="weekly",
        )

        assert report is not None
        assert report.report_type == "weekly"
        assert report.title is not None
        assert report.exercise_summary is not None
        assert report.diet_summary is not None
        assert report.sleep_summary is not None
        assert report.mood_summary is not None
        assert report.health_score is not None
        assert 0 <= report.health_score <= 100

    def test_list_reports(self, report_db, test_user, report_service, sample_health_data):
        """测试列出报告"""
        # 生成一个报告
        report_service.generate_report(
            db=report_db,
            user_id=test_user.id,
            report_type="weekly",
        )

        reports = report_service.list_reports(
            db=report_db,
            user_id=test_user.id,
        )
        assert len(reports) >= 1

    def test_comparison_with_previous(self, report_db, test_user, report_service, sample_health_data):
        """测试与上期的对比"""
        report = report_service.generate_report(
            db=report_db,
            user_id=test_user.id,
            report_type="weekly",
        )
        # 首次报告，comparison 可能为空
        assert report.comparison is not None

    def test_empty_data_report(self, report_db, test_user, report_service):
        """测试无数据时生成报告"""
        report = report_service.generate_report(
            db=report_db,
            user_id=test_user.id,
            report_type="weekly",
        )
        assert report is not None
        assert report.health_score is not None
