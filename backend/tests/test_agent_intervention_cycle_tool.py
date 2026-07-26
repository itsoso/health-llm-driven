"""agent intervention_cycle 工具测试 — status / start 确认流程 / 主动提议 / user 隔离.

闭环只在 service 层验证(已有 test_intervention_cycle.py); 这里只验 agent 接线:
工具能驱动 service、写操作走两段式确认、status 讲清进展、用户隔离、提议 blob 门控。
"""
import asyncio
import datetime
import json
import uuid


def _mk_user(db):
    from app.models.user import User
    u = User(
        username=f"ait_{uuid.uuid4().hex[:8]}",
        email=f"ait_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="测试",
        birth_date=datetime.date(1985, 1, 1),
        gender="男",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_exam(db, user_id, items, exam_date):
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    exam = MedicalExam(user_id=user_id, exam_date=exam_date, exam_type="comprehensive",
                       patient_gender="男", patient_age=41)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    for name, val, unit in items:
        db.add(MedicalExamItem(exam_id=exam.id, item_name=name, value=val, unit=unit, source="manual"))
    db.commit()
    db.refresh(exam)
    return exam


def _exec(db, user_id, args):
    from app.services.agent_executor import AgentExecutor
    ex = AgentExecutor(db)
    ex._current_user_id = user_id
    return asyncio.run(ex._exec_intervention_cycle(args))


def _seed_abnormal_labs(db, user_id):
    """LDL 3.8(高) + 尿酸 600(男, 高) + 甘油三酯 5.0(高) + ALT 26(正常) → 异常杠杆 LDL/UA/TG。

    R16(2026-06-26)扩门控后 LDL 与 UA 都成处方/药物混杂指标(门控),TG(甘油三酯)是
    生活方式主导的**非门控**指标,留作"保留描述式裁决(改善中 + Δ)"的正例。
    """
    from app.services.biomarker_service import ingest_exam
    e = _mk_exam(db, user_id, [
        ("低密度脂蛋白", 3.8, "mmol/L"),
        ("尿酸", 600, "µmol/L"),
        ("甘油三酯", 5.0, "mmol/L"),
        ("谷丙转氨酶", 26, "U/L"),
    ], datetime.date(2026, 3, 1))
    ingest_exam(db, e)


# ── status ─────────────────────────────────────────────

def test_status_no_active_cycle_friendly(db):
    u = _mk_user(db)
    out = _exec(db, u.id, {"action": "status"})
    assert "没有进行中的干预周期" in out


def test_status_reports_baseline_latest_delta(db):
    from app.services.intervention_cycle_service import start_metabolic_cycle, record_recheck
    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    twin = {"meta": {"data_sources": ["labs"]}}
    cycle = start_metabolic_cycle(db, u.id, twin, days=90, start_date=datetime.date(2026, 3, 1))
    assert cycle.outcomes  # 异常项纳入

    # 复查: LDL 3.8→3.0, 尿酸 600→450 (两者门控→需医生评估), 甘油三酯 5.0→2.0 = -60% 超 RCV(~55%)
    # 且仍 >目标1.7 → 改善中(非门控保留描述式裁决 + Δ)
    _mk_exam(db, u.id, [
        ("低密度脂蛋白", 3.0, "mmol/L"),
        ("尿酸", 450, "µmol/L"),
        ("甘油三酯", 2.0, "mmol/L"),
    ], datetime.date(2026, 6, 1))
    from app.services.biomarker_service import ingest_exam
    from app.models.medical_exam import MedicalExam
    latest_exam = db.query(MedicalExam).filter(
        MedicalExam.user_id == u.id, MedicalExam.exam_date == datetime.date(2026, 6, 1)
    ).first()
    ingest_exam(db, latest_exam)
    record_recheck(db, cycle, twin)

    out = _exec(db, u.id, {"action": "status"})
    assert "基线 → 最新" in out
    # baseline → latest 出现(门控指标仍展示用户自己的事实值, 只中和裁决/变化幅度)
    assert "3.8" in out and "3.0" in out      # LDL
    assert "600" in out and "450" in out      # UA
    assert "5.0" in out and "2.0" in out      # TG
    # 非门控 TG: 保留描述式裁决 + Δ
    assert "Δ" in out
    assert "改善中" in out    # 甘油三酯朝目标方向但未达标(非门控 → 保留描述式裁决)
    # R16:LDL + UA 都是处方/药物混杂指标 → 门控为「需医生评估」,不外吐达标/改善裁决与变化幅度
    assert "需医生评估" in out
    # 防回归:门控的 UA 这一行绝不出"改善中"(它向目标移动了, 旧行为会误报改善)
    ua_line = next((ln for ln in out.splitlines() if "尿酸" in ln), "")
    assert ua_line and "需医生评估" in ua_line and "改善中" not in ua_line and "Δ" not in ua_line


# ── start: 两段式确认 ─────────────────────────────────────

def test_start_requires_confirmation_first(db):
    from app.services.intervention_cycle_service import get_active_cycle
    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    out = _exec(db, u.id, {"action": "start"})
    assert "[NEEDS_CONFIRMATION]" in out
    # 未确认 → 绝不建周期
    assert get_active_cycle(db, u.id) is None


def test_start_confirmed_creates_cycle_via_service(db):
    from app.services.agent_executor import _write_receipt_from_tool_result
    from app.services.intervention_cycle_service import get_active_cycle
    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    out = _exec(db, u.id, {"action": "start", "confirmed": True, "days": 90})
    receipt = json.loads(out)
    assert "已开启" in out
    cycle = get_active_cycle(db, u.id)
    assert cycle is not None
    assert receipt["id"] == cycle.id
    assert receipt["resource_type"] == "intervention_cycle"
    assert receipt["status"] == "verified"
    runtime_receipt = _write_receipt_from_tool_result(
        "intervention_cycle", None, out
    )
    assert runtime_receipt is not None
    assert runtime_receipt["resource_id"] == str(cycle.id)
    assert cycle.status == "active"
    assert cycle.baseline_snapshot_id is not None
    # 目标非空 (异常 LDL/UA 锁进结局)
    assert len(cycle.outcomes) >= 1
    codes = {om.metric_code for om in cycle.outcomes}
    assert "lipid_ldl" in codes or "UA" in codes


def test_start_no_double_open(db):
    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    _exec(db, u.id, {"action": "start", "confirmed": True})
    out2 = _exec(db, u.id, {"action": "start", "confirmed": True})
    receipt = json.loads(out2)
    assert "已经有一个进行中的干预周期" in out2
    from app.models.intervention_cycle import InterventionCycle
    n = db.query(InterventionCycle).filter(
        InterventionCycle.user_id == u.id, InterventionCycle.status == "active"
    ).count()
    assert n == 1
    assert receipt["id"]
    assert receipt["resource_type"] == "intervention_cycle"


def test_list_cycles_returns_history(db):
    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    _exec(db, u.id, {"action": "start", "confirmed": True})

    out = _exec(db, u.id, {"action": "list", "status": "all", "limit": 10})

    assert "干预周期历史" in out
    assert "active" in out
    assert "#" in out


def test_update_cycle_requires_confirmation_then_adjusts_days(db):
    from app.services.intervention_cycle_service import get_active_cycle

    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    _exec(db, u.id, {"action": "start", "confirmed": True, "days": 90})
    cycle = get_active_cycle(db, u.id)
    old_end = cycle.planned_end_date

    first = _exec(db, u.id, {"action": "update", "cycle_id": cycle.id, "days": 120})
    assert "[NEEDS_CONFIRMATION]" in first
    db.refresh(cycle)
    assert cycle.planned_end_date == old_end

    second = _exec(db, u.id, {
        "action": "update",
        "cycle_id": cycle.id,
        "days": 120,
        "confirmed": True,
    })
    receipt = json.loads(second)
    db.refresh(cycle)
    assert "已调整" in second
    assert receipt["id"] == cycle.id
    assert receipt["resource_type"] == "intervention_cycle"
    assert cycle.planned_end_date == cycle.start_date + datetime.timedelta(days=120)


def test_cancel_cycle_requires_confirmation_then_abandons(db):
    from app.services.intervention_cycle_service import get_active_cycle

    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    _exec(db, u.id, {"action": "start", "confirmed": True})
    cycle = get_active_cycle(db, u.id)

    first = _exec(db, u.id, {"action": "cancel", "cycle_id": cycle.id})
    assert "[NEEDS_CONFIRMATION]" in first
    db.refresh(cycle)
    assert cycle.status == "active"

    second = _exec(db, u.id, {
        "action": "cancel",
        "cycle_id": cycle.id,
        "confirmed": True,
        "reason": "用户决定重新规划",
    })
    receipt = json.loads(second)
    db.refresh(cycle)
    assert "已取消" in second
    assert receipt["id"] == cycle.id
    assert receipt["resource_type"] == "intervention_cycle"
    assert cycle.status == "abandoned"
    assert get_active_cycle(db, u.id) is None


# ── user 隔离 ───────────────────────────────────────────

def test_user_isolation_status(db):
    u1 = _mk_user(db)
    u2 = _mk_user(db)
    _seed_abnormal_labs(db, u1.id)
    _exec(db, u1.id, {"action": "start", "confirmed": True})
    # u2 看不到 u1 的周期
    out = _exec(db, u2.id, {"action": "status"})
    assert "没有进行中的干预周期" in out


# ── 主动提议 blob 门控 ───────────────────────────────────

def test_proposal_blob_when_abnormal_and_no_cycle(db):
    from app.services.intervention_cycle_service import intervention_proposal_prompt_blob
    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    blob = intervention_proposal_prompt_blob(db, u.id)
    assert "干预闭环主动提议" in blob
    assert "intervention_cycle" in blob


def test_proposal_blob_suppressed_when_active_cycle(db):
    from app.services.intervention_cycle_service import intervention_proposal_prompt_blob
    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    _exec(db, u.id, {"action": "start", "confirmed": True})
    # 已有周期 → 不再提议
    assert intervention_proposal_prompt_blob(db, u.id) == ""


def test_proposal_blob_empty_when_no_abnormal_levers(db):
    from app.services.intervention_cycle_service import intervention_proposal_prompt_blob
    u = _mk_user(db)
    # 没有任何化验 → 无异常杠杆
    assert intervention_proposal_prompt_blob(db, u.id) == ""


# ── 未知 action ─────────────────────────────────────────

def test_unknown_action(db):
    u = _mk_user(db)
    out = _exec(db, u.id, {"action": "bogus"})
    assert json.loads(out) == {
        "status": "rejected",
        "success": False,
        "dispatch_started": False,
        "error_code": "intervention_action_unsupported",
        "message": "当前干预周期操作不受支持。",
    }
