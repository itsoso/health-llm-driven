"""身体成分分析测试 - TDD"""
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.weight import WeightRecord
from app.services.body_composition_service import BodyCompositionService


@pytest.fixture
def bc_db():
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
def test_user(bc_db):
    user = User(username="bc_test", email="bc@test.com", hashed_password="hash", name="测试", is_active=True, is_approved=True)
    bc_db.add(user)
    bc_db.commit()
    bc_db.refresh(user)
    return user


@pytest.fixture
def bc_service():
    return BodyCompositionService()


@pytest.fixture
def sample_records(bc_db, test_user):
    today = date.today()
    for i in range(7):
        r = WeightRecord(
            user_id=test_user.id,
            record_date=today - timedelta(days=6 - i),
            weight=70.0 + i * 0.2,
            body_fat_percentage=20.0 - i * 0.3,
            muscle_mass_kg=30.0 + i * 0.1,
            visceral_fat=8,
            bone_mass_kg=3.2,
            water_percentage=55.0 + i * 0.2,
            bmi=23.5 + i * 0.1,
        )
        bc_db.add(r)
    bc_db.commit()


class TestBodyCompositionService:
    def test_get_trend(self, bc_db, test_user, bc_service, sample_records):
        """测试获取趋势数据"""
        result = bc_service.get_composition_trend(bc_db, test_user.id, days=7)
        assert len(result["data_points"]) == 7
        assert result["summary"]["current_weight"] is not None
        assert result["summary"]["weight_change"] is not None
        assert result["summary"]["record_count"] == 7

    def test_get_trend_empty(self, bc_db, test_user, bc_service):
        """测试无数据时的趋势"""
        result = bc_service.get_composition_trend(bc_db, test_user.id, days=7)
        assert result["data_points"] == []

    def test_get_analysis(self, bc_db, test_user, bc_service, sample_records):
        """测试身体成分分析"""
        result = bc_service.get_body_analysis(bc_db, test_user.id)
        assert result["status"] == "ok"
        assert len(result["analysis"]) > 0
        # 检查有 BMI 分析
        metrics = [a["metric"] for a in result["analysis"]]
        assert "BMI" in metrics
        assert "体脂率" in metrics

    def test_analysis_no_data(self, bc_db, test_user, bc_service):
        """测试无数据时的分析"""
        result = bc_service.get_body_analysis(bc_db, test_user.id)
        assert result["status"] == "no_data"

    def test_weight_change_calculation(self, bc_db, test_user, bc_service, sample_records):
        """测试体重变化计算"""
        result = bc_service.get_composition_trend(bc_db, test_user.id, days=7)
        # 7天内体重从70.0增加到71.2
        change = result["summary"]["weight_change"]
        assert change is not None
        assert change > 0

    def test_body_fat_change(self, bc_db, test_user, bc_service, sample_records):
        """测试体脂率变化"""
        result = bc_service.get_composition_trend(bc_db, test_user.id, days=7)
        # 体脂从20.0下降
        if "body_fat_change" in result["summary"]:
            assert result["summary"]["body_fat_change"] < 0
