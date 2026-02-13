"""女性健康测试 - TDD"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.womens_health import MenstrualCycle, CycleSymptom
from app.services.womens_health_service import WomensHealthService


@pytest.fixture
def wh_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def wh_user(wh_db):
    user = User(username="wh_test", email="wh@test.com", hashed_password="hash", name="女性测试", is_active=True, is_approved=True)
    wh_db.add(user)
    wh_db.commit()
    wh_db.refresh(user)
    return user


@pytest.fixture
def wh_service():
    return WomensHealthService()


@pytest.fixture
def sample_cycles(wh_db, wh_user):
    """创建3个月的周期数据"""
    today = date.today()
    cycles = []
    for i in range(3):
        start = today - timedelta(days=28 * (3 - i))
        cycle = MenstrualCycle(
            user_id=wh_user.id,
            start_date=start,
            end_date=start + timedelta(days=5),
            cycle_length=28,
            period_length=5,
            flow_intensity="moderate",
            notes=f"第{i + 1}个周期",
        )
        wh_db.add(cycle)
        cycles.append(cycle)
    wh_db.commit()
    for c in cycles:
        wh_db.refresh(c)
    return cycles


class TestMenstrualCycleModel:
    def test_create_cycle(self, wh_db, wh_user):
        """测试创建周期记录"""
        cycle = MenstrualCycle(
            user_id=wh_user.id,
            start_date=date.today(),
            period_length=5,
            flow_intensity="moderate",
        )
        wh_db.add(cycle)
        wh_db.commit()
        wh_db.refresh(cycle)
        assert cycle.id is not None

    def test_create_symptom(self, wh_db, wh_user, sample_cycles):
        """测试创建症状记录"""
        symptom = CycleSymptom(
            user_id=wh_user.id,
            cycle_id=sample_cycles[0].id,
            record_date=sample_cycles[0].start_date,
            symptom_type="cramps",
            severity=3,
            notes="腹痛",
        )
        wh_db.add(symptom)
        wh_db.commit()
        wh_db.refresh(symptom)
        assert symptom.id is not None


class TestWomensHealthService:
    def test_start_period(self, wh_db, wh_user, wh_service):
        """测试记录经期开始"""
        cycle = wh_service.start_period(
            db=wh_db,
            user_id=wh_user.id,
            start_date=date.today(),
            flow_intensity="moderate",
        )
        assert cycle.start_date == date.today()
        assert cycle.flow_intensity == "moderate"

    def test_end_period(self, wh_db, wh_user, wh_service, sample_cycles):
        """测试记录经期结束"""
        latest = sample_cycles[-1]
        # 删除 end_date 模拟正在进行的周期
        latest.end_date = None
        wh_db.commit()

        result = wh_service.end_period(wh_db, wh_user.id, latest.id, date.today())
        assert result is not None
        assert result.end_date is not None
        assert result.period_length is not None

    def test_get_cycles(self, wh_db, wh_user, wh_service, sample_cycles):
        """测试获取周期列表"""
        cycles = wh_service.get_cycles(wh_db, wh_user.id, limit=10)
        assert len(cycles) == 3

    def test_predict_next_period(self, wh_db, wh_user, wh_service, sample_cycles):
        """测试预测下次经期"""
        prediction = wh_service.predict_next_period(wh_db, wh_user.id)
        assert prediction is not None
        assert "predicted_start" in prediction
        assert "predicted_end" in prediction
        assert "avg_cycle_length" in prediction

    def test_predict_no_data(self, wh_db, wh_user, wh_service):
        """测试无数据时的预测"""
        prediction = wh_service.predict_next_period(wh_db, wh_user.id)
        assert prediction is None

    def test_log_symptom(self, wh_db, wh_user, wh_service, sample_cycles):
        """测试记录症状"""
        symptom = wh_service.log_symptom(
            db=wh_db,
            user_id=wh_user.id,
            data={
                "record_date": str(date.today()),
                "symptom_type": "cramps",
                "severity": 4,
                "notes": "严重腹痛",
            },
        )
        assert symptom.symptom_type == "cramps"
        assert symptom.severity == 4

    def test_get_cycle_stats(self, wh_db, wh_user, wh_service, sample_cycles):
        """测试获取周期统计"""
        stats = wh_service.get_cycle_stats(wh_db, wh_user.id)
        assert "avg_cycle_length" in stats
        assert "avg_period_length" in stats
        assert "total_cycles" in stats
        assert stats["total_cycles"] == 3

    def test_get_calendar(self, wh_db, wh_user, wh_service, sample_cycles):
        """测试获取日历数据"""
        today = date.today()
        cal = wh_service.get_calendar(wh_db, wh_user.id, today.year, today.month)
        assert "year" in cal
        assert "month" in cal
        assert "period_days" in cal
        assert isinstance(cal["period_days"], list)
