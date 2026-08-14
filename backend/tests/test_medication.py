"""用药管理测试 - TDD"""
import pytest
from datetime import date, timedelta, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.medication import Medication, MedicationLog
from app.services.medication_service import MedicationService
from app.utils.timezone import get_user_today


@pytest.fixture
def med_db():
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
def med_user(med_db):
    user = User(username="med_test", email="med@test.com", hashed_password="hash", name="用药测试", is_active=True, is_approved=True)
    med_db.add(user)
    med_db.commit()
    med_db.refresh(user)
    return user


@pytest.fixture
def med_service():
    return MedicationService()


@pytest.fixture
def sample_medication(med_db, med_user):
    """创建示例药品"""
    med = Medication(
        user_id=med_user.id,
        name="布洛芬",
        dosage="400mg",
        frequency="每日2次",
        times_per_day=2,
        reminder_times=["08:00", "20:00"],
        start_date=date.today() - timedelta(days=7),
        notes="饭后服用",
        is_active=True,
    )
    med_db.add(med)
    med_db.commit()
    med_db.refresh(med)
    return med


class TestMedicationModel:
    def test_create_medication(self, med_db, med_user):
        """测试创建药品"""
        med = Medication(
            user_id=med_user.id,
            name="阿莫西林",
            dosage="500mg",
            frequency="每日3次",
            times_per_day=3,
            start_date=date.today(),
            is_active=True,
        )
        med_db.add(med)
        med_db.commit()
        med_db.refresh(med)
        assert med.id is not None
        assert med.name == "阿莫西林"
        assert med.times_per_day == 3

    def test_create_log(self, med_db, med_user, sample_medication):
        """测试创建服药记录"""
        log = MedicationLog(
            user_id=med_user.id,
            medication_id=sample_medication.id,
            taken_date=date.today(),
            taken_time="08:00",
            status="taken",
        )
        med_db.add(log)
        med_db.commit()
        med_db.refresh(log)
        assert log.id is not None
        assert log.status == "taken"


class TestMedicationService:
    def test_add_medication(self, med_db, med_user, med_service):
        """测试添加药品"""
        result = med_service.add_medication(
            db=med_db,
            user_id=med_user.id,
            data={
                "name": "维生素D",
                "dosage": "1000IU",
                "frequency": "每日1次",
                "times_per_day": 1,
                "reminder_times": ["09:00"],
                "notes": "早餐后",
            },
        )
        assert result.name == "维生素D"
        assert result.is_active is True

    def test_list_medications(self, med_db, med_user, med_service, sample_medication):
        """测试列出药品"""
        meds = med_service.list_medications(med_db, med_user.id)
        assert len(meds) >= 1
        assert any(m.name == "布洛芬" for m in meds)

    def test_update_medication(self, med_db, med_user, med_service, sample_medication):
        """测试更新药品"""
        result = med_service.update_medication(
            db=med_db,
            medication_id=sample_medication.id,
            user_id=med_user.id,
            data={"dosage": "200mg"},
        )
        assert result is not None
        assert result.dosage == "200mg"

    def test_deactivate_medication(self, med_db, med_user, med_service, sample_medication):
        """测试停用药品"""
        result = med_service.deactivate_medication(
            db=med_db,
            medication_id=sample_medication.id,
            user_id=med_user.id,
        )
        assert result is True
        med = med_service.get_medication(med_db, sample_medication.id, med_user.id)
        assert med.is_active is False

    def test_log_taken(self, med_db, med_user, med_service, sample_medication):
        """测试记录服药"""
        log = med_service.log_medication(
            db=med_db,
            user_id=med_user.id,
            medication_id=sample_medication.id,
            taken_time="08:00",
            status="taken",
        )
        assert log.status == "taken"
        assert log.taken_date == get_user_today(med_db, med_user.id)

    def test_log_skipped(self, med_db, med_user, med_service, sample_medication):
        """测试跳过服药"""
        log = med_service.log_medication(
            db=med_db,
            user_id=med_user.id,
            medication_id=sample_medication.id,
            taken_time="08:00",
            status="skipped",
            skip_reason="副作用",
        )
        assert log.status == "skipped"
        assert log.skip_reason == "副作用"

    def test_get_today_status(self, med_db, med_user, med_service, sample_medication):
        """测试获取今日服药状态"""
        # 先记录一次
        med_service.log_medication(med_db, med_user.id, sample_medication.id, "08:00", "taken")

        status = med_service.get_today_status(med_db, med_user.id)
        assert len(status) >= 1
        med_status = next(s for s in status if s["medication_id"] == sample_medication.id)
        assert med_status["taken_count"] == 1
        assert med_status["total_count"] == 2  # times_per_day = 2

    def test_get_adherence_stats(self, med_db, med_user, med_service, sample_medication):
        """测试获取服药依从性统计"""
        # 记录几天的数据
        for i in range(3):
            d = date.today() - timedelta(days=i)
            log = MedicationLog(
                user_id=med_user.id,
                medication_id=sample_medication.id,
                taken_date=d,
                taken_time="08:00",
                status="taken",
            )
            med_db.add(log)
        med_db.commit()

        stats = med_service.get_adherence_stats(med_db, med_user.id, days=7)
        assert "adherence_rate" in stats
        assert "total_taken" in stats
        assert stats["total_taken"] >= 3

    def test_delete_not_own(self, med_db, med_user, med_service, sample_medication):
        """测试不能操作别人的药品"""
        result = med_service.deactivate_medication(
            db=med_db, medication_id=sample_medication.id, user_id=999,
        )
        assert result is False


class TestTakenTimeNormalization:
    """2026-07-12 生产实锤回归:完整 ISO(微秒+时区,32 字符)曾溢出
    medication_logs.taken_time varchar → 500 → 无写回执 → 用药确认流看似失灵。
    列语义 = "HH:MM"(幂等去重槽 + 剂次槽解析都按它),归一化是单一正解。"""

    def test_normalize_full_iso_with_microseconds_tz(self):
        from app.services.medication_service import normalize_taken_time
        # 生产事故原始 payload(32 字符)→ 北京时刻 HH:MM
        assert normalize_taken_time("2026-07-12T14:14:23.101115+08:00") == "14:14"

    def test_normalize_tz_conversion_to_beijing(self):
        from app.services.medication_service import normalize_taken_time
        # UTC 06:14 = 北京 14:14
        assert normalize_taken_time("2026-07-12T06:14:23+00:00") == "14:14"

    def test_normalize_short_forms(self):
        from app.services.medication_service import normalize_taken_time
        assert normalize_taken_time("08:00") == "08:00"
        assert normalize_taken_time("8:5") == "08:05"
        assert normalize_taken_time("14:14:23") == "14:14"
        assert normalize_taken_time(None) is None
        assert normalize_taken_time("  ") is None

    def test_normalize_garbage_fail_loud(self):
        import pytest as _pytest
        from app.services.medication_service import normalize_taken_time
        with _pytest.raises(ValueError):
            normalize_taken_time("昨天早上")
        with _pytest.raises(ValueError):
            normalize_taken_time("25:99")

    def test_api_accepts_full_iso_and_stores_hhmm(self, client, db, auth_user_and_headers, sample_medication_payload=None):
        user, headers = auth_user_and_headers
        med = client.post("/api/v1/medication/medications", headers=headers, json={
            "name": "回归测试药", "frequency": "qd",
        }).json()
        res = client.post("/api/v1/medication/logs", headers=headers, json={
            "medication_id": med["id"],
            "taken_time": "2026-07-12T14:14:23.101115+08:00",  # 事故原始形状
            "status": "taken",
        })
        assert res.status_code == 200, res.text
        assert res.json()["taken_time"] == "14:14"

    def test_api_garbage_taken_time_is_422_not_500(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        med = client.post("/api/v1/medication/medications", headers=headers, json={
            "name": "回归测试药2", "frequency": "qd",
        }).json()
        res = client.post("/api/v1/medication/logs", headers=headers, json={
            "medication_id": med["id"],
            "taken_time": "昨天早上",
            "status": "taken",
        })
        assert res.status_code == 422
