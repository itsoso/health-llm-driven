"""agent intervention_cycle 工具测试 — status / start 确认流程 / 主动提议 / user 隔离.

闭环只在 service 层验证(已有 test_intervention_cycle.py); 这里只验 agent 接线:
工具能驱动 service、写操作走两段式确认、status 讲清进展、用户隔离、提议 blob 门控。
"""
import asyncio
import datetime
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
    db.add(exam); db.commit(); db.refresh(exam)
    for name, val, unit in items:
        db.add(MedicalExamItem(exam_id=exam.id, item_name=name, value=val, unit=unit, source="manual"))
    db.commit(); db.refresh(exam)
    return exam


def _exec(db, user_id, args):
    from app.services.agent_executor import AgentExecutor
    ex = AgentExecutor(db)
    ex._current_user_id = user_id
    return asyncio.run(ex._exec_intervention_cycle(args))


def _seed_abnormal_labs(db, user_id):
    """LDL 3.8(高) + 尿酸 460(男, 高) + ALT 26(正常) → 异常杠杆 LDL/UA。"""
    from app.services.biomarker_service import ingest_exam
    e = _mk_exam(db, user_id, [
        ("低密度脂蛋白", 3.8, "mmol/L"),
        ("尿酸", 460, "µmol/L"),
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

    # 复查: LDL 降到 3.0(达标), 尿酸降到 430(改善中)
    _mk_exam(db, u.id, [
        ("低密度脂蛋白", 3.0, "mmol/L"),
        ("尿酸", 430, "µmol/L"),
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
    # baseline → latest 出现
    assert "3.8" in out and "3.0" in out
    assert "460" in out and "430" in out
    # delta + 状态中文标注
    assert "Δ" in out
    assert "达标" in out      # LDL 命中目标
    assert "改善中" in out    # 尿酸朝目标方向但未达标


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
    from app.services.intervention_cycle_service import get_active_cycle
    u = _mk_user(db)
    _seed_abnormal_labs(db, u.id)
    out = _exec(db, u.id, {"action": "start", "confirmed": True, "days": 90})
    assert "已开启" in out
    cycle = get_active_cycle(db, u.id)
    assert cycle is not None
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
    assert "已经有一个进行中的干预周期" in out2
    from app.models.intervention_cycle import InterventionCycle
    n = db.query(InterventionCycle).filter(
        InterventionCycle.user_id == u.id, InterventionCycle.status == "active"
    ).count()
    assert n == 1


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
    assert out.startswith("Error:")
