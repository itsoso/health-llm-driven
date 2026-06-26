"""InterventionCycle 干预闭环测试 (Personal Health OS P2, G4)."""
import datetime
import uuid


def _mk_user(db):
    from app.models.user import User
    u = User(
        username=f"ic_{uuid.uuid4().hex[:8]}",
        email=f"ic_{uuid.uuid4().hex[:8]}@example.com",
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


def test_metabolic_cycle_lifecycle(db):
    from app.services.biomarker_service import ingest_exam
    from app.services.intervention_cycle_service import (
        start_metabolic_cycle, record_recheck, get_active_cycle,
    )
    u = _mk_user(db)
    twin = {"meta": {"data_sources": ["labs", "garmin"]}}

    # 基线: LDL 4.5(高,留出超 RCV 又不达标的空间), UA 460(男, 高), ALT 26(正常)
    e1 = _mk_exam(db, u.id, [
        ("低密度脂蛋白", 4.5, "mmol/L"),
        ("尿酸", 460, "µmol/L"),
        ("谷丙转氨酶", 26, "U/L"),
    ], datetime.date(2026, 3, 1))
    ingest_exam(db, e1)

    cycle = start_metabolic_cycle(db, u.id, twin, days=90, start_date=datetime.date(2026, 3, 1))
    assert cycle.status == "active"
    assert cycle.baseline_snapshot_id is not None
    assert cycle.planned_end_date == datetime.date(2026, 3, 1) + datetime.timedelta(days=90)
    assert cycle.stop_conditions and len(cycle.stop_conditions) >= 1

    codes = {om.metric_code for om in cycle.outcomes}
    assert "lipid_ldl" in codes and "UA" in codes   # 异常项纳入目标
    assert "ALT" not in codes                        # 正常项不纳入

    ldl = next(om for om in cycle.outcomes if om.metric_code == "lipid_ldl")
    assert ldl.baseline_value == 4.5
    assert ldl.target_value == 3.0
    assert ldl.status == "pending"
    assert get_active_cycle(db, u.id).id == cycle.id

    # 复查: LDL 3.3 (4.5→3.3 = -26.7% 超 RCV~23% 且仍 >目标3.0 → improving), UA 370 (≤380 → met)
    e2 = _mk_exam(db, u.id, [
        ("低密度脂蛋白", 3.3, "mmol/L"),
        ("尿酸", 370, "µmol/L"),
    ], datetime.date(2026, 6, 1))
    ingest_exam(db, e2)

    record_recheck(db, cycle, twin)
    ldl = next(om for om in cycle.outcomes if om.metric_code == "lipid_ldl")
    ua = next(om for om in cycle.outcomes if om.metric_code == "UA")
    assert ldl.latest_value == 3.3
    assert ldl.delta == round(3.3 - 4.5, 3)
    assert ldl.delta_pct is not None and ldl.delta_pct < 0
    assert ldl.status == "improving"
    # R16 P2:单次复查的 LDL 是稀疏化验(基线+复查各 1 点)→ 端点无法平滑(method=none)→
    # 置信度封 low(2 个单点不足以高置信;真信号靠 P3/P4 重复测量挣)。变化仍判显著(超 RCV)。
    assert ldl.significant is True and ldl.confidence == "low"
    assert ldl.smoothing_method == "none"
    assert ua.latest_value == 370
    assert ua.status == "met"


def test_within_noise_change_is_flat_low_confidence(db):
    """R16 去噪:LDL 小幅变化(未超 RCV)→ flat + 低置信(不臆断见效)。"""
    from app.services.biomarker_service import ingest_exam
    from app.services.intervention_cycle_service import start_metabolic_cycle, record_recheck
    u = _mk_user(db)
    twin = {"meta": {"data_sources": ["labs"]}}
    ingest_exam(db, _mk_exam(db, u.id, [("低密度脂蛋白", 3.8, "mmol/L")], datetime.date(2026, 3, 1)))
    cycle = start_metabolic_cycle(db, u.id, twin)
    # 3.8→3.5 = -7.9%,远低于 LDL RCV~23% → 噪声带内
    ingest_exam(db, _mk_exam(db, u.id, [("低密度脂蛋白", 3.5, "mmol/L")], datetime.date(2026, 6, 1)))
    record_recheck(db, cycle, twin)
    ldl = next(om for om in cycle.outcomes if om.metric_code == "lipid_ldl")
    assert ldl.status == "flat"
    assert ldl.significant is False and ldl.confidence == "low"
    assert cycle.latest_snapshot_id is not None
    assert cycle.latest_snapshot_id != cycle.baseline_snapshot_id


def test_explicit_targets_and_missing_observation(db):
    from app.services.intervention_cycle_service import start_metabolic_cycle
    u = _mk_user(db)
    twin = {"meta": {"data_sources": ["labs"]}}
    # 显式目标, 但无任何 observation → baseline None, pending
    cycle = start_metabolic_cycle(
        db, u.id, twin,
        target_specs=[{"code": "lipid_ldl", "target": 3.0, "direction": "down"}],
    )
    assert len(cycle.outcomes) == 1
    om = cycle.outcomes[0]
    assert om.baseline_value is None
    assert om.status == "pending"


def test_worsening_status(db):
    from app.services.biomarker_service import ingest_exam
    from app.services.intervention_cycle_service import start_metabolic_cycle, record_recheck
    u = _mk_user(db)
    twin = {"meta": {"data_sources": ["labs"]}}
    e1 = _mk_exam(db, u.id, [("低密度脂蛋白", 3.6, "mmol/L")], datetime.date(2026, 3, 1))
    ingest_exam(db, e1)
    cycle = start_metabolic_cycle(db, u.id, twin)
    # 3.6→4.6 = +27.8% 超 RCV~23% → 确属恶化
    e2 = _mk_exam(db, u.id, [("低密度脂蛋白", 4.6, "mmol/L")], datetime.date(2026, 6, 1))
    ingest_exam(db, e2)
    record_recheck(db, cycle, twin)
    ldl = next(om for om in cycle.outcomes if om.metric_code == "lipid_ldl")
    assert ldl.delta > 0
    assert ldl.status == "worsening"
    assert ldl.significant is True
