"""A3 — 用药安全预检(DDI/PGx/DSI)必须看见正在录入的药 (passed-db, 非 build_twin SessionLocal)。

回归根因 (memory project_build_twin_sessionlocal_ignores_db):
  旧 `_medication_safety_alerts` 走 `build_twin(db, ...)`,其 Phase-B 并行 filler 各自
  `SessionLocal()` 自开**生产引擎**连接,忽略传入的请求 `db`。在 CI/测试下(生产引擎指向
  另一个空的 in-memory SQLite、且无人 create_all),这个 SessionLocal 看不到测试 db 里
  刚 commit 的药 → DDI/PGx 预检对着空药单跑 → 返回 [] = **静默 under-alarm**:用户加了
  会出血相互作用的药,系统却说"无告警"。

  迁移后:预检改用传入 db 的 targeted filler(_fill_medication + DSI/PGx 分区),看得见
  请求事务里的药 → DDI 命中 → 阻断/提示正常。

RED-GREEN:在旧 build_twin 路径上,test_warfarin_nsaid_precheck_sees_added_drug 应 FAIL
(alerts 为空);迁移后应 PASS。
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.user import User
from app.models.medication import Medication, MedicationLog
from app.api.medication import _medication_safety_alerts
from app.utils.timezone import get_user_today


@pytest.fixture
def safety_db():
    """独立 in-memory SQLite(StaticPool 单连接),模拟请求事务 db。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
def safety_user(safety_db):
    user = User(
        username="ddi_precheck",
        email="ddi@test.com",
        hashed_password="hash",
        name="DDI预检",
        is_active=True,
        is_approved=True,
    )
    safety_db.add(user)
    safety_db.commit()
    safety_db.refresh(user)
    return user


def _add_med(db, user_id: int, name: str) -> Medication:
    med = Medication(
        user_id=user_id,
        name=name,
        frequency="每日2次",
        times_per_day=2,
        start_date=date.today() - timedelta(days=1),
        is_active=True,
    )
    db.add(med)
    db.commit()
    db.refresh(med)
    return med


def test_warfarin_nsaid_precheck_sees_added_drug(safety_db, safety_user):
    """加华法林 + 布洛芬(NSAID)→ DDI 预检必须命中出血风险告警。

    核心断言:预检看得见**通过传入 db 录入**的药。旧 build_twin 路径下,
    并行 SessionLocal 看不到 safety_db 的药 → 此断言失败(under-alarm)。
    """
    _add_med(safety_db, safety_user.id, "华法林")
    _add_med(safety_db, safety_user.id, "布洛芬")

    alerts = _medication_safety_alerts(safety_db, safety_user.id)

    # 必须命中华法林×出血风险药 DDI(category=ddi)
    ddi_rule_ids = {a["rule_id"] for a in alerts if a.get("category") == "ddi"}
    assert "ddi.warfarin_bleeding" in ddi_rule_ids, (
        f"用药安全预检漏报正在录入的华法林×NSAID 出血风险 = under-alarm。"
        f"实际 alerts={[a.get('rule_id') for a in alerts]}"
    )


def test_precheck_includes_inactive_medication_taken_today_without_reactivating(
    safety_db, safety_user,
):
    """A taken log is an exposure fact even when its medication definition is inactive."""
    _add_med(safety_db, safety_user.id, "华法林")
    ibuprofen = _add_med(safety_db, safety_user.id, "布洛芬")
    ibuprofen.is_active = False
    safety_db.add(MedicationLog(
        user_id=safety_user.id,
        medication_id=ibuprofen.id,
        taken_date=get_user_today(safety_db, safety_user.id),
        taken_time="08:00",
        status="taken",
        actual_dosage="一粒",
    ))
    safety_db.commit()

    alerts = _medication_safety_alerts(safety_db, safety_user.id)

    assert "ddi.warfarin_bleeding" in {a["rule_id"] for a in alerts}
    safety_db.refresh(ibuprofen)
    assert ibuprofen.is_active is False


def test_no_interaction_no_false_alert(safety_db, safety_user):
    """单药(维生素D)无相互作用 → DDI 预检不应误报(回归:迁移后不引入假阳)。"""
    _add_med(safety_db, safety_user.id, "维生素D")

    alerts = _medication_safety_alerts(safety_db, safety_user.id)

    ddi_rule_ids = {a["rule_id"] for a in alerts if a.get("category") == "ddi"}
    assert "ddi.warfarin_bleeding" not in ddi_rule_ids


def test_empty_meds_returns_no_alerts(safety_db, safety_user):
    """无任何药 → 预检返回空列表,不抛、不误报(回归)。"""
    alerts = _medication_safety_alerts(safety_db, safety_user.id)
    assert isinstance(alerts, list)
    assert all(a.get("category") in {"pgx", "ddi", "dsi"} for a in alerts)


def test_partition_fill_failure_is_fail_loud(
    safety_db, safety_user, monkeypatch, caplog,
):
    """分区填充抛错 → 绝不静默返回 [](under-alarm),而是注入 fail-safe advisory。

    护栏断言:模拟 fill_medication_safety_partitions 抛错(填充失败),预检必须
    返回带 medication.safety_precheck_incomplete 的 HIGH advisory,让客户端感知
    "未裁决",绝不冒充"无告警=安全"。
    """
    import app.services.medication_safety as medication_safety

    sensitive_exception_text = "simulated crash mentioning 华法林"

    def _boom(*args, **kwargs):
        raise RuntimeError(sensitive_exception_text)

    monkeypatch.setattr(
        medication_safety.twin_builder, "fill_medication_safety_partitions", _boom
    )

    alerts = _medication_safety_alerts(safety_db, safety_user.id)

    rule_ids = {a["rule_id"] for a in alerts}
    assert "medication.safety_precheck_incomplete" in rule_ids, (
        f"填充失败被静默吞成空列表 = under-alarm。实际 alerts={[a.get('rule_id') for a in alerts]}"
    )
    advisory = next(a for a in alerts if a["rule_id"] == "medication.safety_precheck_incomplete")
    assert advisory["requires_medical_attention"] is True
    assert sensitive_exception_text not in caplog.text
    assert "RuntimeError" in caplog.text


def test_rule_evaluation_failure_is_fail_loud_without_sensitive_exception_text(
    safety_db, safety_user, monkeypatch, caplog,
):
    """Rule crashes add an advisory but never leak medication-bearing exception text."""
    import app.services.medication_safety as medication_safety

    sensitive_exception_text = "rule crash while evaluating 华法林"

    def _boom(_twin):
        raise ValueError(sensitive_exception_text)

    monkeypatch.setattr(medication_safety, "evaluate_rules_with_status", _boom)

    alerts = _medication_safety_alerts(safety_db, safety_user.id)

    assert "medication.safety_precheck_incomplete" in {a["rule_id"] for a in alerts}
    assert sensitive_exception_text not in caplog.text
    assert "ValueError" in caplog.text


def test_partial_rule_failure_redacts_dependency_exception_text(
    safety_db, safety_user, caplog,
):
    """Per-rule isolation must not leak its medication-bearing exception text."""
    from app.agents.safety_guardian.engine import registry

    sensitive_exception_text = "partial rule crash mentioning 华法林"

    def _boom(_twin):
        raise RuntimeError(sensitive_exception_text)

    saved = list(registry._rules)
    registry.register(_boom)
    try:
        alerts = _medication_safety_alerts(safety_db, safety_user.id)
    finally:
        registry._rules[:] = saved

    assert "medication.safety_precheck_incomplete" in {a["rule_id"] for a in alerts}
    assert sensitive_exception_text not in caplog.text
    assert "failed_rule_count=1" in caplog.text


def test_medication_read_failure_is_fail_loud(safety_db, safety_user, monkeypatch):
    """读药(get_today_status)抛错 → 必须 fail-loud,绝不退化成空药单 → 假装无相互作用。

    护栏(safety review 抓到的 BLOCKING):medication 分区是 DDI/PGx/DSI 全部规则的 gate,
    若读药失败被吞成 active_meds=[],所有规则早返回 → 看似干净 = under-alarm(与 SessionLocal
    盲读同类)。迁移后 raise_on_error 路径直读 get_today_status、不吞异常 → 读失败注入
    fail-safe advisory。

    旧实现(_fill_medication 吞异常)上本断言失败(无 advisory);fail-loud 修复后通过。
    """
    from app.services.medication_service import MedicationService

    # 录入一个真会触发 DDI 的药对,确保"若能读到药"本应命中告警 —— 但读药被打断。
    _add_med(safety_db, safety_user.id, "华法林")
    _add_med(safety_db, safety_user.id, "布洛芬")

    def _boom(self, db, user_id):
        raise RuntimeError("simulated medication read crash")

    monkeypatch.setattr(MedicationService, "get_today_status", _boom)

    alerts = _medication_safety_alerts(safety_db, safety_user.id)

    rule_ids = {a["rule_id"] for a in alerts}
    assert "medication.safety_precheck_incomplete" in rule_ids, (
        f"读药失败被静默吞成空药单 = under-alarm(DDI 全部早返回)。"
        f"实际 alerts={[a.get('rule_id') for a in alerts]}"
    )
