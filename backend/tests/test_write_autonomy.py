"""Write 自治层首切片(③):allowlist 仅 measurement_prompt 自动执行,严守安全 gate。

mock _safety_blocks_autonomy 隔离 build_twin(它自开 SessionLocal 看不到测试库);
gate 逻辑(allowlist / 开关 / 安全门抑制 / 每日上限 / fail-safe)是这里的被测对象。
"""
from app.models.smart_reminder import SmartReminder
from app.models.write_intent import WriteIntent
from app.services import write_autonomy
from tests.conftest import create_authenticated_user


def _add_measurement_wi(db, uid, target_type="measurement_bp", kind="measurement_prompt"):
    wi = WriteIntent(
        user_id=uid, kind=kind, title="今天还没测血压", status="pending",
        trust_tier="manual_confirm", target_type=target_type, target_id=None,
        payload={"metric": "bp", "remind_at": None},
    )
    db.add(wi)
    db.commit()
    db.refresh(wi)
    return wi


def _no_critical(monkeypatch):
    monkeypatch.setattr("app.services.write_autonomy._safety_blocks_autonomy", lambda db, uid: False)


def test_is_autonomy_allowlisted_only_measurement_prompt():
    assert write_autonomy.is_autonomy_allowlisted("measurement_prompt")
    # 医疗级 / 依从 / 预约 / 下单 / 闹钟 / 复购 全部禁止自治
    for k in ["adherence_nudge", "doctor_booking", "food_order", "alarm_set",
              "checkup_reminder", "recheck_due", "reorder_nudge", "hearing_health_task"]:
        assert not write_autonomy.is_autonomy_allowlisted(k), f"{k} 不得在 allowlist"


def test_measurement_prompt_auto_executes(db, monkeypatch):
    _no_critical(monkeypatch)
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)
    res = write_autonomy.auto_execute_pending(db, user.id)
    assert res["auto_executed"] == 1 and res["reason"] == "ok"
    db.refresh(wi)
    assert wi.status == "executed" and wi.trust_tier == "auto"
    assert wi.executed_ref and wi.executed_ref.startswith("smart_reminder:")
    # 产物可逆:已建 SmartReminder(用户可 dismiss),非凭空写医疗记录
    rem = db.query(SmartReminder).filter(SmartReminder.user_id == user.id).first()
    assert rem is not None and rem.extra_data.get("write_intent_id") == wi.id
    # 自治产物 low 优先级:静音 + 尊重勿扰(未人确认,不该睡眠窗带声推)
    assert rem.priority == "low"


def test_non_allowlisted_kind_never_auto(db, monkeypatch):
    _no_critical(monkeypatch)
    user, _ = create_authenticated_user(db)
    # adherence_nudge 是最危险诱惑(自治写依从→污染 DDI/PGx)——必须永不自治
    wi = _add_measurement_wi(db, user.id, kind="adherence_nudge", target_type="medication")
    res = write_autonomy.auto_execute_pending(db, user.id)
    assert res["auto_executed"] == 0
    db.refresh(wi)
    assert wi.status == "pending" and wi.trust_tier == "manual_confirm"


def test_disabled_flag_no_auto(db, monkeypatch):
    _no_critical(monkeypatch)
    monkeypatch.setattr(write_autonomy.settings, "write_autonomy_enabled", False)
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)
    res = write_autonomy.auto_execute_pending(db, user.id)
    assert res == {"auto_executed": 0, "reason": "disabled"}
    db.refresh(wi)
    assert wi.status == "pending"


def test_safety_gate_blocks_auto(db, monkeypatch):
    # 安全门(CRITICAL 或规则失败)阻断 → 一切让位,不自治
    monkeypatch.setattr("app.services.write_autonomy._safety_blocks_autonomy", lambda db, uid: True)
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)
    res = write_autonomy.auto_execute_pending(db, user.id)
    assert res["reason"] == "safety_gate_blocked" and res["auto_executed"] == 0
    db.refresh(wi)
    assert wi.status == "pending"


def test_safety_gate_suppresses_on_failed_rule_count(db, monkeypatch):
    # 评审 BLOCKING:某 CRITICAL 规则崩了被吞(critical_count=0 但 failed_rule_count>0)→ 必须抑制。
    # write_autonomy 懒导入 build_twin / evaluate_rules_with_status,故 patch 各自源模块。
    monkeypatch.setattr(
        "app.twin.builder.build_twin", lambda db, uid, use_cache=True: object(), raising=False
    )
    monkeypatch.setattr(
        "app.agents.safety_guardian.engine.evaluate_rules_with_status",
        lambda twin: ([], 1),  # 0 alerts 但 1 条规则失败
    )
    user, _ = create_authenticated_user(db)
    assert write_autonomy._safety_blocks_autonomy(db, user.id) is True


def test_safety_gate_fail_safe_on_exception(db, monkeypatch):
    # 安全检查本身抛异常 → fail-safe 抑制(不默许自治)
    monkeypatch.setattr(
        "app.twin.builder.build_twin",
        lambda db, uid, use_cache=True: (_ for _ in ()).throw(RuntimeError("twin boom")),
        raising=False,
    )
    user, _ = create_authenticated_user(db)
    assert write_autonomy._safety_blocks_autonomy(db, user.id) is True


def test_daily_cap_enforced(db, monkeypatch):
    _no_critical(monkeypatch)
    user, _ = create_authenticated_user(db)
    for i in range(write_autonomy.AUTONOMY_DAILY_CAP + 2):
        _add_measurement_wi(db, user.id, target_type=f"measurement_{i}")
    res = write_autonomy.auto_execute_pending(db, user.id)
    assert res["auto_executed"] == write_autonomy.AUTONOMY_DAILY_CAP
    # 今天已满额 → 再调 0
    res2 = write_autonomy.auto_execute_pending(db, user.id)
    assert res2 == {"auto_executed": 0, "reason": "daily_cap"}
