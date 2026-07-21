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


# ───────────────────────── 治理 NIT-3:自治写审计记录 ─────────────────────────


def test_autonomous_write_logs_audit_row(db, monkeypatch):
    """每条自治执行落一条 write_autonomy/autonomous_write 审计记录(系统"无人确认即写"可审计)。"""
    from app.models.agent_audit_log import AgentAuditLog

    _no_critical(monkeypatch)
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)
    res = write_autonomy.auto_execute_pending(db, user.id)
    assert res["auto_executed"] == 1
    db.refresh(wi)
    row = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.user_id == user.id,
            AgentAuditLog.agent_type == "write_autonomy",
            AgentAuditLog.action == "autonomous_write",
        )
        .one()
    )
    d = row.result_detail
    assert d["intent_id"] == wi.id
    assert d["kind"] == "measurement_prompt"
    assert d["trust_tier"] == "auto"
    assert d["executed_ref"] == wi.executed_ref and d["executed_ref"].startswith("smart_reminder:")


def test_no_audit_row_when_no_autonomous_write(db, monkeypatch):
    """非 allowlist kind 不自治 → 不应留下自治写审计记录(审计只记真发生的自治写)。"""
    from app.models.agent_audit_log import AgentAuditLog

    _no_critical(monkeypatch)
    user, _ = create_authenticated_user(db)
    _add_measurement_wi(db, user.id, kind="adherence_nudge", target_type="medication")
    write_autonomy.auto_execute_pending(db, user.id)
    assert (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.user_id == user.id, AgentAuditLog.agent_type == "write_autonomy")
        .count()
        == 0
    )


# ───────────────────────── cap-TOCTOU #3:每日上限硬保证 ─────────────────────────


def test_reserve_slot_hard_cap(db):
    """连续预留至多 CAP 个,第 CAP+1 起原子拒绝(并发各算 budget 也无法越过 CAP)。"""
    from app.utils.timezone import get_china_today

    user, _ = create_authenticated_user(db)
    today = get_china_today()
    oks = [
        write_autonomy._reserve_autonomy_slot(db, user.id, today)
        for _ in range(write_autonomy.AUTONOMY_DAILY_CAP + 3)
    ]
    assert sum(oks) == write_autonomy.AUTONOMY_DAILY_CAP
    assert oks[: write_autonomy.AUTONOMY_DAILY_CAP] == [True] * write_autonomy.AUTONOMY_DAILY_CAP
    assert oks[write_autonomy.AUTONOMY_DAILY_CAP :] == [False, False, False]


def test_reserve_slot_seeds_from_real_executions(db):
    """计数行首次创建用今日真实已执行数做种子 → 部署当天/历史执行叠加新执行不越过 CAP。"""
    from datetime import datetime, timezone

    from app.models.autonomy_daily_counter import AutonomyDailyCounter
    from app.utils.timezone import get_china_today

    user, _ = create_authenticated_user(db)
    # 预置 2 条今日已自治执行的 WriteIntent(模拟部署前/历史)
    for i in range(2):
        db.add(
            WriteIntent(
                user_id=user.id, kind="measurement_prompt", title="x", status="executed",
                trust_tier="auto", target_type=f"hist_{i}",
                decided_at=datetime.now(timezone.utc),
            )
        )
    db.commit()
    today = get_china_today()
    oks = [
        write_autonomy._reserve_autonomy_slot(db, user.id, today)
        for _ in range(write_autonomy.AUTONOMY_DAILY_CAP)
    ]
    # 种子=2 → 只剩 CAP-2 个额度
    assert sum(oks) == write_autonomy.AUTONOMY_DAILY_CAP - 2
    row = db.query(AutonomyDailyCounter).filter_by(user_id=user.id, day=today).first()
    assert row is not None and row.count == write_autonomy.AUTONOMY_DAILY_CAP


def test_idempotent_confirm_releases_slot(db, monkeypatch):
    """confirm 返回幂等(未真正执行)→ 归还额度,不白吃今日预算。"""
    from app.models.autonomy_daily_counter import AutonomyDailyCounter
    from app.utils.timezone import get_china_today

    _no_critical(monkeypatch)
    user, _ = create_authenticated_user(db)
    _add_measurement_wi(db, user.id)
    monkeypatch.setattr(
        "app.services.write_intent_service.confirm",
        lambda db, uid, iid, trust_tier=None: {"id": iid, "status": "executed", "idempotent": True},
    )
    res = write_autonomy.auto_execute_pending(db, user.id)
    assert res["auto_executed"] == 0
    row = db.query(AutonomyDailyCounter).filter_by(user_id=user.id, day=get_china_today()).first()
    assert row is not None and row.count == 0  # 预留后归还,额度未被吃掉


def test_confirm_trust_tier_only_on_winning_claim(db):
    """confirm(trust_tier='auto') 只在赢得原子认领时翻档;对已被人确认执行的意图(幂等)不误标 auto。"""
    from app.services import write_intent_service as svc

    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)
    r1 = svc.confirm(db, user.id, wi.id)  # 人确认(不传 trust_tier)
    assert r1["status"] == "executed" and not r1["idempotent"]
    db.refresh(wi)
    assert wi.trust_tier == "manual_confirm"
    r2 = svc.confirm(db, user.id, wi.id, trust_tier="auto")  # 自治档再确认 → 幂等
    assert r2["idempotent"] is True
    db.refresh(wi)
    assert wi.trust_tier == "manual_confirm"  # 未被误标 auto(只随赢得认领的那条翻档)


# ═══════════════════════ B 承重墙:NEVER 硬集 / 门档表 / 挣权钩子 / 后台 worker ═══════════════════════


def _patch_worker_session(monkeypatch, db):
    """让后台 worker 的 `with SessionLocal() as db` 接到 test db(不真连库)。"""
    from app.tasks import write_autonomy_worker as task_mod

    class _CM:
        def __enter__(self_inner):
            return db

        def __exit__(self_inner, *a):
            return False

    monkeypatch.setattr(task_mod, "SessionLocal", lambda: _CM())


# ───────────── (4) NEVER 硬集:即便 NEVER kind 误进 allowlist 仍硬拦(红绿) ─────────────


def test_never_kind_hard_blocked_even_if_in_allowlist(db, monkeypatch):
    """红绿核心:把 adherence_nudge(NEVER kind)**强行塞进 allowlist**,auto 路径**仍**拒绝自治执行。

    护住 PRD #11 belt-and-suspenders:`_is_auto_eligible` = `kind ∈ allowlist ∧ kind ∉ NEVER`。
    删掉 NEVER 这道检查 → 本测试转红(adherence_nudge 会被自治写,污染依从)。恢复 → 绿。
    """
    _no_critical(monkeypatch)
    # 故意把危险 kind 加进 allowlist(模拟「有人误改 allowlist」)+ 让 runtime hook 也返回它
    poisoned = frozenset({"measurement_prompt", "adherence_nudge"})
    monkeypatch.setattr(write_autonomy, "AUTONOMY_ALLOWLIST", poisoned)
    monkeypatch.setattr(
        write_autonomy, "runtime_autonomy_allowlist", lambda db, uid: poisoned
    )
    user, _ = create_authenticated_user(db)
    bad = _add_measurement_wi(db, user.id, kind="adherence_nudge", target_type="medication")
    good = _add_measurement_wi(db, user.id, kind="measurement_prompt", target_type="measurement_bp")

    res = write_autonomy.auto_execute_pending(db, user.id)
    # 良性 measurement_prompt 仍自治执行;adherence_nudge 被 NEVER 硬拦,维持 pending 留人确认。
    assert res["auto_executed"] == 1
    db.refresh(bad)
    db.refresh(good)
    assert bad.status == "pending" and bad.trust_tier == "manual_confirm", \
        "NEVER kind 绝不能被自治执行(即便误进 allowlist)"
    assert good.status == "executed" and good.trust_tier == "auto"


def test_is_auto_eligible_two_gates():
    """`_is_auto_eligible` = allowlist ∩ ¬NEVER 的纯函数门(两道正交)。"""
    allow = frozenset({"measurement_prompt", "adherence_nudge"})
    # in allowlist 但 in NEVER → 拒
    assert write_autonomy._is_auto_eligible("adherence_nudge", allow) is False
    # in allowlist 且 not in NEVER → 准
    assert write_autonomy._is_auto_eligible("measurement_prompt", allow) is True
    # not in allowlist → 拒
    assert write_autonomy._is_auto_eligible("recheck_due", allow) is False


def test_never_set_covers_all_clinical_financial_kinds():
    """NEVER 集合显式覆盖临床/依从/财务/外部动作类 kind(PRD #11 固化,只增不减)。"""
    for k in ["adherence_nudge", "medication_intake_batch", "food_order",
              "doctor_booking", "alarm_set", "reorder_nudge", "checkup_reminder",
              "recheck_due", "hearing_health_task"]:
        assert k in write_autonomy.NEVER_AUTONOMY_KINDS, f"{k} 必须在 NEVER 集合"
    # measurement_prompt 是唯一可自治 kind,不在 NEVER 里
    assert "measurement_prompt" not in write_autonomy.NEVER_AUTONOMY_KINDS


# ───────────── (5) runtime 挣权钩子:B v1 恒返回静态集 ─────────────


def test_runtime_allowlist_equals_static_set_in_b(db):
    """B v1:runtime_autonomy_allowlist 无收敛数据,恒 == 静态 {measurement_prompt}(C 的接口,今日零升级)。"""
    user, _ = create_authenticated_user(db)
    eff = write_autonomy.runtime_autonomy_allowlist(db, user.id)
    assert eff == write_autonomy.AUTONOMY_ALLOWLIST == frozenset({"measurement_prompt"})


# ───────────── (3) 每 kind 安全门档位表:measurement_prompt=CRITICAL,默认 HIGH ─────────────


def test_gate_tier_table_measurement_critical_default_high():
    assert write_autonomy._gate_tier_for("measurement_prompt") == "CRITICAL"
    # 未登记 kind → 更严默认 HIGH(未来 kind 自动走更严门)
    assert write_autonomy._gate_tier_for("some_future_kind") == "HIGH"


def test_safety_gate_high_tier_suppresses_on_high_alert(db, monkeypatch):
    """HIGH 门:有 HIGH(非 CRITICAL)告警时抑制;CRITICAL 门则放行同一 HIGH 告警(档位差异生效)。"""
    from app.agents.safety_guardian.schema import Severity

    class _A:
        def __init__(self, sev):
            self.severity = sev

    monkeypatch.setattr(
        "app.twin.builder.build_twin", lambda db, uid, use_cache=True: object(), raising=False
    )
    monkeypatch.setattr(
        "app.agents.safety_guardian.engine.evaluate_rules_with_status",
        lambda twin: ([_A(Severity.HIGH)], 0),  # 1 条 HIGH 告警,0 规则失败
    )
    user, _ = create_authenticated_user(db)
    # HIGH 门 → 抑制
    assert write_autonomy._safety_blocks_autonomy(db, user.id, tier="HIGH") is True
    # CRITICAL 门 → 不抑制(HIGH < CRITICAL),measurement_prompt 仍可自治(首切片行为)
    assert write_autonomy._safety_blocks_autonomy(db, user.id, tier="CRITICAL") is False
    # fail-safe:未知/拼写错 tier → 走更严 HIGH 门(抑制),绝不因异常字符串放松成 CRITICAL
    assert write_autonomy._safety_blocks_autonomy(db, user.id, tier="oops_typo") is True


def test_gate_tier_typo_falls_back_to_high_not_critical(db, monkeypatch):
    """Codex capstone BLOCKING #2(红绿):_GATE_TIER_BY_KIND 里 measurement_prompt 配成拼写错值 →
    批 reducer 必须 collapse 到更严 HIGH 门(不得落到更松 CRITICAL)。否则 tier 配错就放松了门:
    内部 _safety_blocks_autonomy 的"未知→HIGH"兜底被绕过(reducer 显式传了 CRITICAL)。

    红绿:把 reducer 改回 `any(==HIGH) else CRITICAL` → 本测试转红(typo→CRITICAL 门放行 HIGH 告警 → 自治执行)。
    """
    from app.agents.safety_guardian.schema import Severity

    class _A:
        def __init__(self, sev):
            self.severity = sev

    # measurement_prompt 的门档配成拼写错(既非 HIGH 也非 CRITICAL)
    monkeypatch.setitem(write_autonomy._GATE_TIER_BY_KIND, "measurement_prompt", "oops_typo")
    # 安全评估:1 条 HIGH 告警、0 规则失败 —— CRITICAL 门放行、HIGH 门抑制(用真 _safety_blocks_autonomy)
    monkeypatch.setattr(
        "app.twin.builder.build_twin", lambda db, uid, use_cache=True: object(), raising=False
    )
    monkeypatch.setattr(
        "app.agents.safety_guardian.engine.evaluate_rules_with_status",
        lambda twin: ([_A(Severity.HIGH)], 0),
    )
    user, _ = create_authenticated_user(db)
    _add_measurement_wi(db, user.id)
    res = write_autonomy.auto_execute_pending(db, user.id)
    # typo tier → 必 collapse 到 HIGH 门 → HIGH 告警抑制自治(绝不因配错放松)
    assert res["auto_executed"] == 0 and res["reason"] == "safety_gate_blocked"


def test_cap_slot_not_released_when_confirm_raises_after_commit(db, monkeypatch):
    """Codex capstone BLOCKING #1(红绿):confirm 在 db.commit() **之后**抛(refresh/旁路闪断)→
    写已落库(status=executed),自治路径**不得**归还额度,否则并发 sweep 复用槽 → 越 CAP(破"硬保证")。

    红绿:把 except 块改回无条件 `_release_autonomy_slot` → 本测试转红(count 被错误减回 0)。
    """
    from app.models.autonomy_daily_counter import AutonomyDailyCounter
    from app.models.write_intent import WriteIntent as _WI
    from app.utils.timezone import get_china_today

    _no_critical(monkeypatch)
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)

    def _confirm_then_boom(db, uid, iid, trust_tier=None):
        # 模拟 confirm 的"已提交"效果:翻 executed 并 commit(写落库),再抛(模拟 commit 后 refresh 闪断)。
        row = db.query(_WI).filter(_WI.id == iid, _WI.user_id == uid).first()
        row.status = "executed"
        row.trust_tier = trust_tier or row.trust_tier
        db.commit()
        raise RuntimeError("post-commit refresh boom")

    monkeypatch.setattr("app.services.write_intent_service.confirm", _confirm_then_boom)

    res = write_autonomy.auto_execute_pending(db, user.id)
    # confirm 抛 → 不计成功执行数,但写确实落库 → 额度已消费不归还。
    assert res["auto_executed"] == 0
    db.refresh(wi)
    assert wi.status == "executed", "confirm 在 commit 后抛 → 写已落库"
    row = db.query(AutonomyDailyCounter).filter_by(user_id=user.id, day=get_china_today()).first()
    assert row is not None and row.count == 1, \
        "confirm 在 commit 后抛 → 额度已消费,绝不得归还(保 CAP 硬保证)"


# ───────────── (1) 后台 Celery worker:无 HTTP 请求自动执行 measurement_prompt ─────────────


def test_bg_worker_auto_executes_measurement_prompt(db, monkeypatch):
    """后台 worker 不经任何 HTTP 请求,对 pending measurement_prompt 跑同一 gate/cap/priority=low 自治执行。"""
    from app.tasks.write_autonomy_worker import run_write_autonomy_sweep

    _no_critical(monkeypatch)
    _patch_worker_session(monkeypatch, db)
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)

    res = run_write_autonomy_sweep()
    assert res["users_scanned"] == 1 and res["total_auto_executed"] == 1
    db.refresh(wi)
    assert wi.status == "executed" and wi.trust_tier == "auto"
    assert wi.executed_ref and wi.executed_ref.startswith("smart_reminder:")
    # 与 GET 路径同款产物:可逆 SmartReminder + low 优先级(未人确认,尊重勿扰)
    rem = db.query(SmartReminder).filter(SmartReminder.user_id == user.id).first()
    assert rem is not None and rem.priority == "low"
    assert rem.extra_data.get("write_intent_id") == wi.id


def test_bg_worker_skips_when_disabled(db, monkeypatch):
    """全局关闭 → worker 早退,不执行任何自治写。"""
    from app.tasks.write_autonomy_worker import run_write_autonomy_sweep

    _patch_worker_session(monkeypatch, db)
    monkeypatch.setattr(write_autonomy.settings, "write_autonomy_enabled", False)
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)
    res = run_write_autonomy_sweep()
    assert res["total_auto_executed"] == 0
    db.refresh(wi)
    assert wi.status == "pending"


def test_bg_worker_never_kind_not_scanned(db, monkeypatch):
    """后台 worker 候选用户圈定用 allowlist∩¬NEVER —— 只有 NEVER kind pending 的用户不被自治执行。"""
    from app.tasks.write_autonomy_worker import run_write_autonomy_sweep

    _no_critical(monkeypatch)
    _patch_worker_session(monkeypatch, db)
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id, kind="adherence_nudge", target_type="medication")
    res = run_write_autonomy_sweep()
    assert res["total_auto_executed"] == 0
    db.refresh(wi)
    assert wi.status == "pending" and wi.trust_tier == "manual_confirm"


# ───────────── (3) 后台 worker 安全门:failed_rule_count>0 抑制 ─────────────


def test_bg_worker_safety_gate_suppresses(db, monkeypatch):
    """后台 worker 走同一安全门:failed_rule_count>0(吞异常护栏)→ 抑制,不自治。"""
    from app.tasks.write_autonomy_worker import run_write_autonomy_sweep

    _patch_worker_session(monkeypatch, db)
    # 真安全门:某规则崩了被吞(0 alerts 但 1 失败)→ fail-safe 抑制
    monkeypatch.setattr(
        "app.twin.builder.build_twin", lambda db, uid, use_cache=True: object(), raising=False
    )
    monkeypatch.setattr(
        "app.agents.safety_guardian.engine.evaluate_rules_with_status",
        lambda twin: ([], 1),
    )
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)
    res = run_write_autonomy_sweep()
    assert res["total_auto_executed"] == 0
    db.refresh(wi)
    assert wi.status == "pending"


def test_bg_worker_critical_alert_suppresses(db, monkeypatch):
    """后台 worker 安全门:CRITICAL 告警活跃 → 抑制自治(一切让位急症)。"""
    from app.agents.safety_guardian.schema import Severity
    from app.tasks.write_autonomy_worker import run_write_autonomy_sweep

    _patch_worker_session(monkeypatch, db)

    class _A:
        severity = Severity.CRITICAL

    monkeypatch.setattr(
        "app.twin.builder.build_twin", lambda db, uid, use_cache=True: object(), raising=False
    )
    monkeypatch.setattr(
        "app.agents.safety_guardian.engine.evaluate_rules_with_status",
        lambda twin: ([_A()], 0),
    )
    user, _ = create_authenticated_user(db)
    wi = _add_measurement_wi(db, user.id)
    res = run_write_autonomy_sweep()
    assert res["total_auto_executed"] == 0
    db.refresh(wi)
    assert wi.status == "pending"


# ───────────── (3)/(6) 后台 worker 每日上限 + bg/GET 不双写(原子槽) ─────────────


def test_bg_worker_daily_cap_enforced(db, monkeypatch):
    """后台 worker 走同一原子槽:一天至多 CAP 条(超出维持 pending)。"""
    from app.tasks.write_autonomy_worker import run_write_autonomy_sweep

    _no_critical(monkeypatch)
    _patch_worker_session(monkeypatch, db)
    user, _ = create_authenticated_user(db)
    for i in range(write_autonomy.AUTONOMY_DAILY_CAP + 3):
        _add_measurement_wi(db, user.id, target_type=f"measurement_{i}")
    res = run_write_autonomy_sweep()
    assert res["total_auto_executed"] == write_autonomy.AUTONOMY_DAILY_CAP
    # 再扫一次:今日已满 → 0
    res2 = run_write_autonomy_sweep()
    assert res2["total_auto_executed"] == 0


def test_bg_and_get_no_double_execute(db, monkeypatch):
    """bg + GET 都跑也不超 CAP / 不双写:原子槽预留 + confirm 原子认领去重。

    手法:先跑 GET 路径 auto_execute_pending(吃掉若干额度),再跑 bg worker(同 db);
    两路对同一批 pending 的执行总数 ≤ CAP,且每条只被执行一次(无重复 SmartReminder)。
    """
    from app.tasks.write_autonomy_worker import run_write_autonomy_sweep

    _no_critical(monkeypatch)
    _patch_worker_session(monkeypatch, db)
    user, _ = create_authenticated_user(db)
    wis = [
        _add_measurement_wi(db, user.id, target_type=f"measurement_{i}")
        for i in range(write_autonomy.AUTONOMY_DAILY_CAP + 2)
    ]
    # GET 路径先执行
    r_get = write_autonomy.auto_execute_pending(db, user.id)
    # bg worker 再执行剩余 eligible(同 db)
    r_bg = run_write_autonomy_sweep()
    total = r_get["auto_executed"] + r_bg["total_auto_executed"]
    # 两路合计不超 CAP(原子槽硬保证)
    assert total == write_autonomy.AUTONOMY_DAILY_CAP
    # 每条至多执行一次:executed 的 WriteIntent 各自仅 1 条 SmartReminder(无双写)
    executed_ids = [w.id for w in wis if (db.refresh(w) or w.status == "executed")]
    assert len(executed_ids) == write_autonomy.AUTONOMY_DAILY_CAP
    for wid in executed_ids:
        n = (
            db.query(SmartReminder)
            .filter(SmartReminder.extra_data.isnot(None))
            .all()
        )
        # 统计指向该 write_intent 的 SmartReminder 数(应恰好 1)
        cnt = sum(1 for r in n if (r.extra_data or {}).get("write_intent_id") == wid)
        assert cnt == 1, f"write_intent {wid} 被双写成 {cnt} 条 SmartReminder"
