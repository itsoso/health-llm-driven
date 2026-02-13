"""情绪追踪功能测试 - TDD"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.mood import MoodRecord
from app.services.mood_service import MoodService


@pytest.fixture
def mood_db():
    """创建测试数据库"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
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
def test_user(mood_db):
    """创建测试用户"""
    user = User(
        username="mood_test_user",
        email="mood_test@example.com",
        hashed_password="hashed_password",
        name="情绪测试用户",
        is_active=True,
        is_approved=True,
    )
    mood_db.add(user)
    mood_db.commit()
    mood_db.refresh(user)
    return user


@pytest.fixture
def mood_service():
    """创建情绪服务实例"""
    return MoodService()


class TestMoodRecordModel:
    """测试情绪记录模型"""

    def test_create_mood_record(self, mood_db, test_user):
        """测试创建情绪记录"""
        record = MoodRecord(
            user_id=test_user.id,
            record_date=date.today(),
            mood_score=4,
            mood_tags=["开心", "平静"],
            energy_level=4,
            stress_level=2,
            anxiety_level=1,
            sleep_quality=4,
            journal="今天心情不错，运动后感觉很舒适",
            triggers=["运动", "天气好"],
            coping_methods=["运动", "冥想"],
        )
        mood_db.add(record)
        mood_db.commit()
        mood_db.refresh(record)

        assert record.id is not None
        assert record.user_id == test_user.id
        assert record.mood_score == 4
        assert record.mood_tags == ["开心", "平静"]
        assert record.energy_level == 4
        assert record.stress_level == 2
        assert record.journal == "今天心情不错，运动后感觉很舒适"
        assert record.created_at is not None

    def test_mood_score_range(self, mood_db, test_user):
        """测试情绪评分范围"""
        # 有效评分
        for score in [1, 2, 3, 4, 5]:
            record = MoodRecord(
                user_id=test_user.id,
                record_date=date.today() - timedelta(days=score),
                mood_score=score,
            )
            mood_db.add(record)
        mood_db.commit()

        records = mood_db.query(MoodRecord).filter(
            MoodRecord.user_id == test_user.id
        ).all()
        assert len(records) == 5

    def test_query_by_date_range(self, mood_db, test_user):
        """测试按日期范围查询"""
        today = date.today()
        for i in range(10):
            record = MoodRecord(
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                mood_score=3 + (i % 3),
            )
            mood_db.add(record)
        mood_db.commit()

        # 查询最近7天
        start_date = today - timedelta(days=6)
        records = mood_db.query(MoodRecord).filter(
            MoodRecord.user_id == test_user.id,
            MoodRecord.record_date >= start_date,
            MoodRecord.record_date <= today,
        ).all()
        assert len(records) == 7


class TestMoodService:
    """测试情绪服务"""

    def test_create_mood_record(self, mood_db, test_user, mood_service):
        """测试通过服务创建情绪记录"""
        record = mood_service.create_record(
            db=mood_db,
            user_id=test_user.id,
            record_date=date.today(),
            mood_score=4,
            mood_tags=["开心"],
            energy_level=4,
            journal="测试日记",
        )
        assert record.id is not None
        assert record.mood_score == 4
        assert record.mood_tags == ["开心"]

    def test_update_existing_record(self, mood_db, test_user, mood_service):
        """测试更新当天已有记录"""
        today = date.today()

        # 创建初始记录
        record1 = mood_service.create_record(
            db=mood_db,
            user_id=test_user.id,
            record_date=today,
            mood_score=3,
        )

        # 更新记录
        updated = mood_service.update_record(
            db=mood_db,
            record_id=record1.id,
            user_id=test_user.id,
            mood_score=5,
            journal="更新后的日记",
        )
        assert updated.mood_score == 5
        assert updated.journal == "更新后的日记"

    def test_get_records_by_date_range(self, mood_db, test_user, mood_service):
        """测试按日期范围获取记录"""
        today = date.today()
        for i in range(14):
            mood_service.create_record(
                db=mood_db,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                mood_score=(i % 5) + 1,
            )

        # 获取最近7天
        records = mood_service.get_records(
            db=mood_db,
            user_id=test_user.id,
            start_date=today - timedelta(days=6),
            end_date=today,
        )
        assert len(records) == 7

    def test_get_stats(self, mood_db, test_user, mood_service):
        """测试获取统计数据"""
        today = date.today()
        scores = [3, 4, 5, 4, 3, 2, 4]
        tags_list = [
            ["开心"], ["平静"], ["开心", "兴奋"], ["平静"],
            ["焦虑"], ["疲惫", "焦虑"], ["开心"]
        ]
        triggers_list = [
            ["运动"], ["天气好"], ["社交"], ["工作"],
            ["工作", "天气差"], ["工作"], ["运动"]
        ]

        for i, (score, tags, triggers) in enumerate(zip(scores, tags_list, triggers_list)):
            mood_service.create_record(
                db=mood_db,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                mood_score=score,
                mood_tags=tags,
                energy_level=score,
                stress_level=6 - score,
                triggers=triggers,
            )

        stats = mood_service.get_stats(
            db=mood_db,
            user_id=test_user.id,
            days=7,
        )
        assert stats.total_records == 7
        assert stats.avg_mood_score is not None
        assert round(stats.avg_mood_score, 2) == round(sum(scores) / len(scores), 2)
        # 检查情绪分布
        assert stats.mood_distribution.get(4) == 3  # score=4 出现3次
        # 检查最常见标签
        assert stats.top_mood_tags.get("开心") == 3
        # 检查最常见触发因素
        assert stats.top_triggers.get("工作") == 3

    def test_get_calendar(self, mood_db, test_user, mood_service):
        """测试获取情绪日历"""
        today = date.today()
        for i in range(5):
            mood_service.create_record(
                db=mood_db,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                mood_score=4,
                mood_tags=["开心"],
            )

        calendar = mood_service.get_calendar(
            db=mood_db,
            user_id=test_user.id,
            year=today.year,
            month=today.month,
        )
        assert calendar.year == today.year
        assert calendar.month == today.month
        assert calendar.recorded_days >= 1
        assert calendar.avg_mood_score is not None

    def test_delete_record(self, mood_db, test_user, mood_service):
        """测试删除记录"""
        record = mood_service.create_record(
            db=mood_db,
            user_id=test_user.id,
            record_date=date.today(),
            mood_score=3,
        )
        record_id = record.id

        result = mood_service.delete_record(
            db=mood_db,
            record_id=record_id,
            user_id=test_user.id,
        )
        assert result is True

        # 确认已删除
        deleted = mood_db.query(MoodRecord).filter(MoodRecord.id == record_id).first()
        assert deleted is None

    def test_delete_other_user_record(self, mood_db, test_user, mood_service):
        """测试不能删除其他用户的记录"""
        record = mood_service.create_record(
            db=mood_db,
            user_id=test_user.id,
            record_date=date.today(),
            mood_score=3,
        )

        result = mood_service.delete_record(
            db=mood_db,
            record_id=record.id,
            user_id=99999,  # 其他用户
        )
        assert result is False

    def test_get_mood_trend_with_correlation(self, mood_db, test_user, mood_service):
        """测试情绪趋势及相关性分析"""
        today = date.today()
        # 创建模式数据：情绪好时精力也好
        for i in range(7):
            score = 5 - (i % 3)  # 5, 4, 3, 5, 4, 3, 5
            mood_service.create_record(
                db=mood_db,
                user_id=test_user.id,
                record_date=today - timedelta(days=i),
                mood_score=score,
                energy_level=score,
                sleep_quality=score,
            )

        stats = mood_service.get_stats(
            db=mood_db,
            user_id=test_user.id,
            days=7,
        )
        # 相关性应该存在（数据完全正相关）
        assert stats.mood_energy_correlation is not None
        assert stats.mood_energy_correlation > 0.9
        assert stats.mood_sleep_correlation is not None

    def test_empty_stats(self, mood_db, test_user, mood_service):
        """测试无数据时的统计"""
        stats = mood_service.get_stats(
            db=mood_db,
            user_id=test_user.id,
            days=7,
        )
        assert stats.total_records == 0
        assert stats.avg_mood_score is None
