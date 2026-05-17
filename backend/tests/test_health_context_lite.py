"""轻量健康上下文服务测试"""
import pytest
from datetime import date, timedelta
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData
from app.models.weight import WeightRecord
from app.models.illness import IllnessEpisode


@pytest.fixture
def test_user(db):
    user = User(
        username="ctxuser",
        email="ctx@example.com",
        hashed_password="hashed_password",
        name="张三",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_profile(db, test_user):
    profile = UserProfile(
        user_id=test_user.id,
        gender="male",
        birth_date=date(1992, 5, 15),
        height_cm=175.0,
        current_weight_kg=72.5,
        target_weight_kg=68.0,
        chronic_conditions=["鼻炎", "咽炎"],
        current_medications=[{"name": "维生素D"}, {"name": "鱼油"}],
        manual_city="北京",
        use_manual_location=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@pytest.fixture
def test_garmin(db, test_user):
    today = date.today()
    records = []
    for i in range(7):
        g = GarminData(
            user_id=test_user.id,
            record_date=today - timedelta(days=i),
            steps=6000 + i * 500,
            resting_heart_rate=56 + i,
            sleep_score=80 + i,
            total_sleep_duration=400 + i * 10,  # minutes
            stress_level=30 + i,
            body_battery_current=70 - i * 3,
            hrv=50.0 + i,
            hrv_status="balanced" if i < 5 else "low",
            spo2_avg=97.0 - i * 0.3,
        )
        records.append(g)
    db.add_all(records)
    db.commit()
    return records


@pytest.fixture(autouse=True)
def clear_cache():
    """每个测试前清空缓存"""
    from app.services.health_context_lite_service import _context_cache
    _context_cache.clear()
    yield
    _context_cache.clear()


class TestHealthContextLite:

    def test_basic_context(self, db, test_user, test_profile, test_garmin):
        """有完整数据时输出包含所有关键信息"""
        from app.services.health_context_lite_service import build_lite_health_context
        ctx = build_lite_health_context(db, test_user.id)
        assert ctx is not None

        # 用户信息
        assert "张三" in ctx
        assert "男" in ctx
        assert "175cm" in ctx
        assert "72.5kg" in ctx
        assert "目标68kg" in ctx
        assert "BMI" in ctx

        # 慢性病 + 用药
        assert "鼻炎" in ctx
        assert "维生素D" in ctx

        # Garmin 数据
        assert "步数" in ctx
        assert "静息心率" in ctx
        assert "睡眠" in ctx
        assert "HRV" in ctx
        assert "SpO2" in ctx

        # 7 日均值
        assert "7日均值" in ctx

        # 位置
        assert "北京" in ctx

    def test_empty_user(self, db, test_user):
        """无 profile/garmin 时不崩溃，返回最小上下文"""
        from app.services.health_context_lite_service import build_lite_health_context
        ctx = build_lite_health_context(db, test_user.id)
        assert ctx is not None
        assert "张三" in ctx
        # 不应崩溃，即使没有 Garmin 数据
        assert "用户健康档案" in ctx

    def test_cache_hit(self, db, test_user, test_profile):
        """5 分钟内第二次调用返回缓存"""
        from app.services.health_context_lite_service import build_lite_health_context, _context_cache

        ctx1 = build_lite_health_context(db, test_user.id)
        assert test_user.id in _context_cache

        # 修改用户名（但不应反映在缓存结果中）
        test_user.name = "李四"
        db.commit()

        ctx2 = build_lite_health_context(db, test_user.id)
        # 应该返回缓存的内容（仍然是张三）
        assert ctx1 == ctx2
        assert "张三" in ctx2

    def test_with_illness(self, db, test_user, test_profile):
        """活跃病症出现在输出中"""
        from app.services.health_context_lite_service import build_lite_health_context

        illness = IllnessEpisode(
            user_id=test_user.id,
            name="口腔溃疡",
            start_date=date.today() - timedelta(days=3),
            status="active",
            severity=6,
        )
        db.add(illness)
        db.commit()

        ctx = build_lite_health_context(db, test_user.id)
        assert "口腔溃疡" in ctx
        assert "第3天" in ctx
        assert "6/10" in ctx

    def test_no_garmin_data(self, db, test_user, test_profile):
        """没有 Garmin 设备时优雅降级"""
        from app.services.health_context_lite_service import build_lite_health_context

        ctx = build_lite_health_context(db, test_user.id)
        assert ctx is not None
        # 应该有用户信息，但没有 Garmin 行
        assert "张三" in ctx
        assert "7日均值" not in ctx  # 没有 Garmin 趋势数据
        assert "睡眠分数" not in ctx  # 没有 Garmin 睡眠数据
