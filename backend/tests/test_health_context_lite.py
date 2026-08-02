"""轻量健康上下文服务测试"""
import logging
import threading
from datetime import date, datetime, timedelta

import pytest

from app.models.clinical_journal import ClinicalJournalEntry
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData
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
    from app.services import health_context_lite_service

    health_context_lite_service._context_cache.clear()
    getattr(
        health_context_lite_service,
        "_context_cache_entry_generations",
        {},
    ).clear()
    getattr(health_context_lite_service, "_context_generations", {}).clear()
    yield
    health_context_lite_service._context_cache.clear()
    getattr(
        health_context_lite_service,
        "_context_cache_entry_generations",
        {},
    ).clear()
    getattr(health_context_lite_service, "_context_generations", {}).clear()


def _add_clinician_feedback(
    db,
    *,
    user_id: int,
    generated_at: datetime,
    created_by: str = "doctor",
    subjective: str | None = None,
    assessment: str | None = None,
    plan: str | None = None,
    objective: str | None = None,
) -> ClinicalJournalEntry:
    entry = ClinicalJournalEntry(
        user_id=user_id,
        generated_at=generated_at,
        created_by=created_by,
        subjective=subjective,
        assessment=assessment,
        plan=plan,
        objective=objective,
    )
    db.add(entry)
    db.flush()
    return entry


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
        from app.services.health_context_lite_service import (
            build_lite_health_context, _context_cache, INJECTION_FULL,
        )

        ctx1 = build_lite_health_context(db, test_user.id)
        # cache key = (user_id, budget); 不传 intent → FULL 档
        assert (test_user.id, INJECTION_FULL) in _context_cache

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


def test_full_context_recalls_recent_doctor_feedback_with_stable_isolation(
    db,
    test_user,
):
    from app.services.health_context_lite_service import (
        _CLINICIAN_FEEDBACK_RECENT_LIMIT,
        build_lite_health_context,
    )

    other = User(
        username="ctx-clinician-other",
        email="ctx-clinician-other@example.com",
        hashed_password="hashed_password",
        name="上下文隔离用户",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.flush()
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 7, 31, 9),
        assessment="过早记录不应召回",
    )
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 1, 9),
        plan="并列时间较早ID",
    )
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 1, 9),
        assessment="并列时间较晚ID",
    )
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 2, 9),
        subjective="最新医生转述",
        objective="Reva/系统诊断：不应召回 objective",
    )
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 3, 9),
        created_by="orchestrator",
        assessment="编排器私密记录绝不能出现",
    )
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 4, 9),
        created_by="manual",
        assessment="手工私密记录绝不能出现",
    )
    _add_clinician_feedback(
        db,
        user_id=other.id,
        generated_at=datetime(2026, 8, 5, 9),
        assessment="另一用户医生意见绝不能出现",
    )
    db.commit()

    context = build_lite_health_context(db, test_user.id)

    assert context is not None
    assert context.count("用户转述的医生意见") == _CLINICIAN_FEEDBACK_RECENT_LIMIT
    assert context.index("最新医生转述") < context.index("并列时间较晚ID")
    assert context.index("并列时间较晚ID") < context.index("并列时间较早ID")
    assert "过早记录不应召回" not in context
    assert "编排器私密记录绝不能出现" not in context
    assert "手工私密记录绝不能出现" not in context
    assert "另一用户医生意见绝不能出现" not in context
    assert "Reva/系统诊断" not in context


def test_clinician_feedback_omits_blank_fields_and_objective(db, test_user):
    from app.services.health_context_lite_service import (
        _clinician_feedback_context_section,
    )

    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 1, 9),
        subjective=" \n\t ",
        assessment="用户转述的评估原文",
        plan=None,
        objective="系统新增诊断结论不得呈现",
    )
    db.commit()

    section = _clinician_feedback_context_section(db, test_user.id)

    assert "用户转述的医生意见" in section
    assert "评估: 用户转述的评估原文" in section
    assert "摘要:" not in section
    assert "计划:" not in section
    assert "系统新增诊断结论不得呈现" not in section
    assert "None" not in section


def test_clinician_feedback_field_bound_survives_truncation(db, test_user):
    from app.services.health_context_lite_service import (
        _CLINICIAN_FEEDBACK_FIELD_MAX_CHARS,
        _clinician_feedback_context_section,
    )

    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 1, 9),
        subjective="摘" * (_CLINICIAN_FEEDBACK_FIELD_MAX_CHARS + 100),
    )
    db.commit()

    section = _clinician_feedback_context_section(db, test_user.id)

    assert section.count("摘") <= _CLINICIAN_FEEDBACK_FIELD_MAX_CHARS
    assert "…" in section


def test_clinician_feedback_entry_bound_survives_truncation(db, test_user):
    from app.services.health_context_lite_service import (
        _CLINICIAN_FEEDBACK_ENTRY_MAX_CHARS,
        _CLINICIAN_FEEDBACK_FIELD_MAX_CHARS,
        _clinician_feedback_context_section,
    )

    long_text = "医" * (_CLINICIAN_FEEDBACK_FIELD_MAX_CHARS + 100)
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 1, 9),
        subjective=long_text,
        assessment=long_text,
        plan=long_text,
    )
    db.commit()

    section = _clinician_feedback_context_section(db, test_user.id)
    entry_lines = [
        line for line in section.splitlines() if "用户转述的医生意见" in line
    ]

    assert len(entry_lines) == 1
    assert len(entry_lines[0]) <= _CLINICIAN_FEEDBACK_ENTRY_MAX_CHARS
    assert entry_lines[0].endswith("…")


def test_clinician_feedback_section_bound_survives_truncation(db, test_user):
    from app.services.health_context_lite_service import (
        _CLINICIAN_FEEDBACK_ENTRY_MAX_CHARS,
        _CLINICIAN_FEEDBACK_FIELD_MAX_CHARS,
        _CLINICIAN_FEEDBACK_RECENT_LIMIT,
        _CLINICIAN_FEEDBACK_SECTION_MAX_CHARS,
        _clinician_feedback_context_section,
    )

    long_text = "诊" * (_CLINICIAN_FEEDBACK_FIELD_MAX_CHARS + 100)
    for day in range(1, _CLINICIAN_FEEDBACK_RECENT_LIMIT + 1):
        _add_clinician_feedback(
            db,
            user_id=test_user.id,
            generated_at=datetime(2026, 8, day, 9),
            subjective=long_text,
            assessment=long_text,
            plan=long_text,
        )
    db.commit()

    section = _clinician_feedback_context_section(db, test_user.id)
    entry_lines = [
        line for line in section.splitlines() if "用户转述的医生意见" in line
    ]

    assert len(section) <= _CLINICIAN_FEEDBACK_SECTION_MAX_CHARS
    assert len(entry_lines) == _CLINICIAN_FEEDBACK_RECENT_LIMIT
    assert all(
        len(line) <= _CLINICIAN_FEEDBACK_ENTRY_MAX_CHARS for line in entry_lines
    )


def test_full_context_without_doctor_feedback_omits_empty_section(db, test_user):
    from app.services.health_context_lite_service import build_lite_health_context

    context = build_lite_health_context(db, test_user.id)

    assert context is not None
    assert "用户转述的医生意见" not in context


def test_minimal_context_never_queries_or_renders_clinician_feedback(
    db,
    test_user,
    monkeypatch,
):
    from app.services.health_context_lite_service import build_lite_health_context

    original_query = db.query
    clinical_queries = 0

    def query_spy(*entities, **kwargs):
        nonlocal clinical_queries
        if any(entity is ClinicalJournalEntry for entity in entities):
            clinical_queries += 1
        return original_query(*entities, **kwargs)

    monkeypatch.setattr(db, "query", query_spy)

    context = build_lite_health_context(db, test_user.id, intent="什么是腰肌代偿")

    assert context is not None
    assert clinical_queries == 0
    assert "用户转述的医生意见" not in context


def test_invalidate_health_context_rebuilds_stale_full_context(db, test_user):
    from app.services.health_context_lite_service import (
        build_lite_health_context,
        invalidate_health_context,
    )

    initial = build_lite_health_context(db, test_user.id)
    assert initial is not None
    assert "失效后可见的医生意见" not in initial
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 1, 9),
        assessment="失效后可见的医生意见",
    )
    db.commit()

    stale = build_lite_health_context(db, test_user.id)
    invalidate_health_context(test_user.id)
    fresh = build_lite_health_context(db, test_user.id)

    assert stale == initial
    assert fresh is not None
    assert "失效后可见的医生意见" in fresh


def test_invalidate_health_context_is_owner_scoped_and_missing_key_is_noop():
    from app.services.health_context_lite_service import (
        INJECTION_FULL,
        INJECTION_MINIMAL,
        _context_cache,
        invalidate_health_context,
    )

    _context_cache[(7, INJECTION_FULL)] = (1.0, "user-seven-full")
    _context_cache[(7, INJECTION_MINIMAL)] = (1.0, "user-seven-minimal")
    _context_cache[(8, INJECTION_FULL)] = (1.0, "user-eight-full")
    _context_cache[(8, INJECTION_MINIMAL)] = (1.0, "user-eight-minimal")

    invalidate_health_context(999)
    invalidate_health_context(7)

    assert (7, INJECTION_FULL) not in _context_cache
    assert (7, INJECTION_MINIMAL) not in _context_cache
    assert _context_cache[(8, INJECTION_FULL)][1] == "user-eight-full"
    assert _context_cache[(8, INJECTION_MINIMAL)][1] == "user-eight-minimal"


def test_invalidation_during_cache_miss_prevents_stale_build_from_refilling(
    monkeypatch,
):
    from app.services import health_context_lite_service

    user_id = 7007
    build_started = threading.Event()
    release_stale_build = threading.Event()
    call_count = 0

    def controlled_build(_db, _user_id, *, budget):
        nonlocal call_count
        call_count += 1
        assert _user_id == user_id
        assert budget == health_context_lite_service.INJECTION_FULL
        if call_count == 1:
            build_started.set()
            assert release_stale_build.wait(timeout=3)
            return "before-commit-context"
        return "after-commit-context"

    monkeypatch.setattr(
        health_context_lite_service,
        "_build_context",
        controlled_build,
    )
    inflight_result = []
    worker = threading.Thread(
        target=lambda: inflight_result.append(
            health_context_lite_service.build_lite_health_context(None, user_id)
        )
    )
    worker.start()
    try:
        assert build_started.wait(timeout=3)
        cache_key = (user_id, health_context_lite_service.INJECTION_FULL)
        assert cache_key not in health_context_lite_service._context_cache

        health_context_lite_service.invalidate_health_context(user_id)
        release_stale_build.set()
        worker.join(timeout=3)

        assert not worker.is_alive()
        assert inflight_result == ["before-commit-context"]
        assert cache_key not in health_context_lite_service._context_cache
        assert health_context_lite_service.build_lite_health_context(
            None,
            user_id,
        ) == "after-commit-context"
        assert call_count == 2
    finally:
        release_stale_build.set()
        worker.join(timeout=3)


def test_missing_key_invalidation_still_advances_owner_generation():
    from app.services.health_context_lite_service import (
        _context_cache,
        _context_generations,
        invalidate_health_context,
    )

    user_id = 7008
    assert not any(key[0] == user_id for key in _context_cache)
    assert _context_generations.get(user_id, 0) == 0

    invalidate_health_context(user_id)
    invalidate_health_context(user_id)

    assert _context_generations[user_id] == 2


def test_clinician_feedback_query_failure_is_fail_soft_and_log_safe(
    db,
    test_user,
    monkeypatch,
    caplog,
):
    from app.services.health_context_lite_service import (
        _clinician_feedback_context_section,
    )

    private_text = "私密医生查询异常文本"
    original_query = db.query

    def fail_clinical_query(*entities, **kwargs):
        if any(entity is ClinicalJournalEntry for entity in entities):
            raise RuntimeError(private_text)
        return original_query(*entities, **kwargs)

    monkeypatch.setattr(db, "query", fail_clinical_query)
    caplog.set_level(logging.WARNING, logger="app.services.health_context_lite_service")

    section = _clinician_feedback_context_section(db, test_user.id)

    assert section == ""
    assert "operation=load_clinician_feedback" in caplog.text
    assert "RuntimeError" in caplog.text
    assert private_text not in caplog.text


def test_clinician_feedback_format_failure_is_fail_soft_and_log_safe(
    db,
    test_user,
    monkeypatch,
    caplog,
):
    from app.services import health_context_lite_service

    private_text = "私密医生格式异常文本"
    _add_clinician_feedback(
        db,
        user_id=test_user.id,
        generated_at=datetime(2026, 8, 1, 9),
        assessment="待格式化内容",
    )
    db.commit()

    def fail_format(_entry):
        raise ValueError(private_text)

    monkeypatch.setattr(
        health_context_lite_service,
        "_format_clinician_feedback_entry",
        fail_format,
    )
    caplog.set_level(logging.WARNING, logger="app.services.health_context_lite_service")

    section = health_context_lite_service._clinician_feedback_context_section(
        db,
        test_user.id,
    )

    assert section == ""
    assert "operation=load_clinician_feedback" in caplog.text
    assert "ValueError" in caplog.text
    assert private_text not in caplog.text
