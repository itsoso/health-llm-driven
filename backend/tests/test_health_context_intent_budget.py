"""P2 意图分级的个人上下文注入预算 (health_context_lite_service)。

背景 (对比评测实锤): 纯知识题 (如"胃溃疡分几期") 被硬塞"你目前 A1 期,还剩约 37 天"——
因为注入策略一套打所有意图。P2 引入注入档: 纯知识意图 → MINIMAL (只留基础画像,
裁掉具体时序数值); 个人判读意图 / 默认 (intent=None) → FULL (维持现状全量, 零回归)。

关键安全护栏: SafetyGuardian 读 Twin 不读这个 lite context (见 test 末尾断言二者独立),
所以 MINIMAL 裁剪不削弱确定性安全引擎; 且 MINIMAL 仍保留安全相关字段 (慢病/用药/过敏/
用药安全基因)。判据保守 fail-open —— 任何拿不准倒向 FULL。
"""
import pytest
from datetime import date, timedelta

from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData
from app.models.illness import IllnessEpisode
from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.services.health_context_lite_service import (
    build_lite_health_context,
    classify_context_profile,
    classify_injection_budget,
    INJECTION_FULL,
    INJECTION_RECOVERY,
    INJECTION_MINIMAL,
)


@pytest.fixture(autouse=True)
def clear_cache():
    from app.services.health_context_lite_service import _context_cache
    _context_cache.clear()
    yield
    _context_cache.clear()


@pytest.fixture
def user(db):
    u = User(
        username="p2user",
        email="p2@example.com",
        hashed_password="hashed_password",
        name="王五",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def profile(db, user):
    p = UserProfile(
        user_id=user.id,
        gender="male",
        birth_date=date(1990, 3, 10),
        height_cm=178.0,
        current_weight_kg=74.0,
        target_weight_kg=70.0,
        chronic_conditions=["鼻炎", "胃溃疡"],
        current_medications=[{"name": "雷贝拉唑"}],
        allergies=["青霉素"],
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def garmin_today(db, user):
    """今日读数 + 7 日趋势 (具体时序数值, MINIMAL 应裁掉)。"""
    today = date.today()
    records = []
    for i in range(7):
        records.append(GarminData(
            user_id=user.id,
            record_date=today - timedelta(days=i),
            steps=7000 + i * 300,
            resting_heart_rate=58 + i,
            sleep_score=82 + i,
            total_sleep_duration=410 + i * 8,
            stress_level=32 + i,
            body_battery_most_charged=72 - i * 2,
            hrv=48.0 + i,
            hrv_status="balanced",
            spo2_avg=96.0,
        ))
    db.add_all(records)
    db.commit()
    return records


@pytest.fixture
def active_illness(db, user):
    """活跃病症 —— 天数 (第N天) 是具体时序数值, MINIMAL 应裁掉。"""
    ill = IllnessEpisode(
        user_id=user.id,
        name="胃溃疡发作",
        start_date=date.today() - timedelta(days=37),
        status="active",
        severity=5,
    )
    db.add(ill)
    db.commit()
    return ill


@pytest.fixture
def drug_safety_gene(db, user):
    """用药安全基因 —— 安全相关静态标签, MINIMAL 与 FULL 都必须保留。"""
    gp = GeneticProfile(user_id=user.id, test_provider="test", test_date=date(2024, 1, 1))
    db.add(gp)
    db.commit()
    db.refresh(gp)
    v = GeneticVariant(
        user_id=user.id,
        profile_id=gp.id,
        rsid="rs4149056",
        category="drug_sensitivity",
        gene_name="SLCO1B1",
        genotype="CT",
        result_label="他汀肌病风险升高",
        risk_level="high",
        variant_nature="risk",
        evidence_level="A",
    )
    db.add(v)
    db.commit()
    return v


# ──── 分类器单测 ────

class TestClassifyInjectionBudget:
    def test_none_and_empty_default_full(self):
        assert classify_injection_budget(None) == INJECTION_FULL
        assert classify_injection_budget("") == INJECTION_FULL
        assert classify_injection_budget("   ") == INJECTION_FULL

    def test_pure_knowledge_is_minimal(self):
        # 评测真实题面: 纯知识分期题
        assert classify_injection_budget("胃溃疡分几期") == INJECTION_MINIMAL
        assert classify_injection_budget("什么是 PPI") == INJECTION_MINIMAL
        assert classify_injection_budget("他汀的作用机制是什么") == INJECTION_MINIMAL
        assert classify_injection_budget("HRV 正常范围是多少") == INJECTION_MINIMAL

    def test_personal_marker_forces_full(self):
        # 即便含知识词, 只要有个人诉求 → FULL (fail-open 给足上下文)
        assert classify_injection_budget("我的胃溃疡是什么期") == INJECTION_FULL
        assert classify_injection_budget("我该怎么办") == INJECTION_FULL
        assert classify_injection_budget("我这个 PPI 还要吃多久") == INJECTION_FULL
        assert classify_injection_budget("帮我看看我的化验") == INJECTION_FULL

    def test_ambiguous_defaults_full(self):
        # 既非明确知识题也非明确个人诉求 → 保守 FULL
        assert classify_injection_budget("胃不舒服") == INJECTION_FULL
        assert classify_injection_budget("最近睡不好") == INJECTION_FULL


class TestClassifyContextProfile:
    def test_sleep_and_exercise_share_recovery_profile(self):
        assert (
            classify_context_profile("昨晚睡得怎样，今天是否适合锻炼？")
            == INJECTION_RECOVERY
        )

    def test_cross_domain_query_fails_open_to_full(self):
        assert (
            classify_context_profile("综合分析最近睡眠和肝功能趋势")
            == INJECTION_FULL
        )

    def test_pure_knowledge_stays_minimal(self):
        assert classify_context_profile("胃溃疡分几期") == INJECTION_MINIMAL


# ──── build_lite_health_context 注入预算 ────

class TestInjectionBudget:
    def test_recovery_profile_keeps_safety_and_drops_unrelated_sections(
        self, db, user, profile, garmin_today, active_illness, drug_safety_gene
    ):
        from app.models.daily_health import DietRecord, WaterIntake

        db.add(DietRecord(
            user_id=user.id,
            record_date=date.today(),
            meal_type="lunch",
            food_items="米饭和牛肉",
            calories=520,
            protein=28,
        ))
        db.add(WaterIntake(
            user_id=user.id,
            record_date=date.today(),
            amount_ml=600,
        ))
        db.commit()

        ctx = build_lite_health_context(
            db,
            user.id,
            intent="昨晚睡得怎样，今天是否适合锻炼？",
            domain_scoped=True,
        )

        assert ctx is not None
        assert "7日均值" in ctx
        assert "恢复就绪" in ctx
        assert "当前病症" in ctx
        assert "雷贝拉唑" in ctx
        assert "青霉素" in ctx
        assert "今日饮水" not in ctx
        assert "今日饮食" not in ctx
        assert "能量平衡" not in ctx
        assert "基因特征" not in ctx

        from app.services.health_context_lite_service import _context_cache
        _context_cache.clear()
        full_ctx = build_lite_health_context(
            db,
            user.id,
            intent="昨晚睡得怎样，今天是否适合锻炼？",
        )
        assert full_ctx is not None
        # This fixture has intentionally little unrelated data; even so the
        # scoped lane removes at least 10%. Production profiles with memories,
        # supplements and check-ins should save more.
        assert len(ctx) < len(full_ctx) * 0.9

    def test_fact_intent_drops_timeseries(
        self, db, user, profile, garmin_today, active_illness
    ):
        """纯知识意图 → MINIMAL: 无今日读数 / 无病症天数 / 无 7 日趋势。"""
        ctx = build_lite_health_context(db, user.id, intent="胃溃疡分几期")
        assert ctx is not None

        # 具体时序数值必须不出现
        assert "第37天" not in ctx          # 病症天数 (A1期天数分析)
        assert "第37天" not in ctx
        assert "7日均值" not in ctx          # 7 日趋势
        assert "SpO2" not in ctx             # 今日血氧读数
        assert "HRV" not in ctx              # HRV 读数
        assert "恢复就绪" not in ctx          # 恢复评分 (基于今日读数)
        assert "静息心率" not in ctx          # 今日/趋势心率
        assert "今日饮水" not in ctx

    def test_fact_intent_keeps_base_profile(
        self, db, user, profile, garmin_today, active_illness, drug_safety_gene
    ):
        """纯知识意图 → MINIMAL 仍保留基础画像 + 安全相关字段。"""
        ctx = build_lite_health_context(db, user.id, intent="胃溃疡分几期")
        assert ctx is not None

        # 基础画像 (稳定描述, 安全相关)
        assert "王五" in ctx
        assert "男" in ctx
        assert "178cm" in ctx or "178" in ctx
        # 慢病标签 + 用药 + 过敏 —— 安全相关, 必须保留
        assert "鼻炎" in ctx
        assert "胃溃疡" in ctx               # 慢病标签 (来自 profile, 非病症天数)
        assert "雷贝拉唑" in ctx             # 当前用药
        assert "青霉素" in ctx               # 过敏禁忌
        # 用药安全基因 —— 安全相关静态标签, MINIMAL 必须保留
        assert "SLCO1B1" in ctx
        assert "用药安全" in ctx

    def test_state_intent_is_full(
        self, db, user, profile, garmin_today, active_illness
    ):
        """个人判读意图 → FULL: 全量时序数值出现 (与 None 一致)。"""
        ctx = build_lite_health_context(db, user.id, intent="我最近恢复得怎么样，我该怎么调整")
        assert ctx is not None
        assert "7日均值" in ctx
        assert "SpO2" in ctx
        assert "第37天" in ctx               # 病症天数在 FULL 保留

    def test_none_intent_zero_regression(
        self, db, user, profile, garmin_today, active_illness
    ):
        """intent=None (默认) → 与不传 intent 逐字节一致 (零回归)。"""
        from app.services.health_context_lite_service import _context_cache
        ctx_none = build_lite_health_context(db, user.id, intent=None)
        _context_cache.clear()
        ctx_default = build_lite_health_context(db, user.id)
        assert ctx_none == ctx_default
        # 且是全量
        assert "7日均值" in ctx_none
        assert "SpO2" in ctx_none

    def test_minimal_and_full_cached_separately(
        self, db, user, profile, garmin_today
    ):
        """MINIMAL 与 FULL 分开缓存, 不互相污染。"""
        from app.services.health_context_lite_service import _context_cache
        ctx_min = build_lite_health_context(db, user.id, intent="什么是 HRV")
        ctx_full = build_lite_health_context(db, user.id, intent="我的 HRV 怎么样")
        assert ctx_min != ctx_full
        assert (user.id, INJECTION_MINIMAL) in _context_cache
        assert (user.id, INJECTION_FULL) in _context_cache
        assert "7日均值" not in ctx_min
        assert "7日均值" in ctx_full


class TestFullPathByteIdentical:
    def test_full_output_matches_original_function(
        self, db, user, profile, garmin_today, active_illness, drug_safety_gene, tmp_path
    ):
        """FULL 档 (intent=None) 输出与改动前的原函数逐字节一致 (零回归证明)。

        从 git HEAD 取原 health_context_lite_service.py 作为独立模块加载, 在同一
        DB fixture 上对比 build_lite_health_context 输出。conftest 已把 JSONB 适配
        成 SQLite, 所以复用 pytest 的 db fixture 建表可用。
        """
        import importlib.util
        import subprocess
        import sys

        orig_src = subprocess.check_output(
            ["git", "show", "HEAD:backend/app/services/health_context_lite_service.py"],
            text=True,
        )
        orig_file = tmp_path / "orig_lite.py"
        orig_file.write_text(orig_src)

        spec = importlib.util.spec_from_file_location("orig_lite_mod", str(orig_file))
        orig = importlib.util.module_from_spec(spec)
        sys.modules["orig_lite_mod"] = orig
        spec.loader.exec_module(orig)
        orig._context_cache.clear()

        orig_out = orig.build_lite_health_context(db, user.id)

        from app.services.health_context_lite_service import _context_cache
        _context_cache.clear()
        new_out = build_lite_health_context(db, user.id, intent=None)

        assert new_out == orig_out


# ──── 关键安全护栏: SafetyGuardian 独立于 lite context ────

class TestSafetyIndependence:
    def test_safety_engine_reads_twin_not_lite_context(self):
        """SafetyGuardian 规则签名读 HealthTwin, 与 lite context 无耦合。

        源码级证明: engine.RuleFn = Callable[[HealthTwin], ...]; guardian/engine
        不 import health_context_lite_service。因此 MINIMAL 裁剪 lite context
        不可能削弱确定性安全引擎的输入 (安全评估走 /api/v1/safety/me → Twin)。
        """
        import inspect
        from app.agents.safety_guardian import engine, guardian

        engine_src = inspect.getsource(engine)
        guardian_src = inspect.getsource(guardian)
        assert "health_context_lite" not in engine_src
        assert "health_context_lite" not in guardian_src
        assert "build_lite_health_context" not in engine_src
        assert "build_lite_health_context" not in guardian_src
        # 规则输入类型是 HealthTwin
        assert "HealthTwin" in engine_src
