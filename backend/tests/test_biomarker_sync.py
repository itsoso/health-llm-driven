"""biomarker_sync 测试 — medical_indicators → biomarker_observations 打通 (P0③).

覆盖:识别落库 / 不识别跳过(不臆造)/ 幂等不重复 / 跨源去重(exam 优先) /
ensure_biomarkers 双源 / 头号修复:仅 medical_indicators 的用户也能拿到非空周期目标。
"""
import datetime
import uuid


def _mk_user(db):
    from app.models.user import User
    u = User(
        username=f"bs_{uuid.uuid4().hex[:8]}",
        email=f"bs_{uuid.uuid4().hex[:8]}@example.com",
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


def _mk_indicator(db, user_id, name, value, unit, record_date, source="manual"):
    from app.models.family_health import MedicalIndicator
    ind = MedicalIndicator(
        user_id=user_id, name=name, value=value, unit=unit,
        record_date=record_date, source=source,
    )
    db.add(ind)
    db.commit()
    db.refresh(ind)
    return ind


def _obs(db, user_id, code=None):
    from app.models.biomarker_observation import BiomarkerObservation
    q = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user_id)
    if code:
        q = q.filter(BiomarkerObservation.code == code)
    return q.all()


# ── 识别 / 不识别 ────────────────────────────────────────────────────────

def test_recognized_indicator_synced(db):
    from app.services.biomarker_sync import sync_indicators_to_biomarkers
    u = _mk_user(db)
    _mk_indicator(db, u.id, "低密度脂蛋白", 3.8, "mmol/L", datetime.date(2026, 3, 1))

    r = sync_indicators_to_biomarkers(db, u.id)
    assert r["recognized"] == 1
    assert r["written"] == 1

    rows = _obs(db, u.id, "lipid_ldl")
    assert len(rows) == 1
    assert rows[0].normalized_value == 3.8
    assert rows[0].abnormal is True       # 3.8 mmol/L 偏高
    assert rows[0].source == "indicator_sync"


def test_unrecognized_indicator_skipped_not_invented(db):
    from app.services.biomarker_sync import sync_indicators_to_biomarkers
    u = _mk_user(db)
    _mk_indicator(db, u.id, "某不存在的项目xyz", 1.0, "U", datetime.date(2026, 3, 1))

    r = sync_indicators_to_biomarkers(db, u.id)
    assert r["scanned"] == 1
    assert r["recognized"] == 0
    assert r["written"] == 0
    assert _obs(db, u.id) == []           # 不在 definitions → 不臆造


# ── 幂等 ─────────────────────────────────────────────────────────────────

def test_sync_idempotent_no_duplicates(db):
    from app.services.biomarker_sync import sync_indicators_to_biomarkers
    u = _mk_user(db)
    _mk_indicator(db, u.id, "谷丙转氨酶", 26, "U/L", datetime.date(2026, 3, 1))

    sync_indicators_to_biomarkers(db, u.id)
    sync_indicators_to_biomarkers(db, u.id)   # 重跑

    rows = _obs(db, u.id, "ALT")
    assert len(rows) == 1                      # 同 user+code+日历日 → 不重复


# ── 跨源去重:exam 优先,不写重复 ────────────────────────────────────────

def test_cross_source_dedup_exam_wins(db):
    from app.services.biomarker_service import ingest_exam
    from app.services.biomarker_sync import sync_indicators_to_biomarkers
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    u = _mk_user(db)
    day = datetime.date(2026, 3, 1)

    # 结构化体检项:LDL 同日
    exam = MedicalExam(user_id=u.id, exam_date=day, exam_type="comprehensive",
                       patient_gender="男", patient_age=41)
    db.add(exam); db.commit(); db.refresh(exam)
    db.add(MedicalExamItem(exam_id=exam.id, item_name="低密度脂蛋白", value=3.8,
                           unit="mmol/L", source="manual"))
    db.commit(); db.refresh(exam)
    ingest_exam(db, exam)

    # medical_indicators 也有同日 LDL
    _mk_indicator(db, u.id, "低密度脂蛋白", 3.8, "mmol/L", day)
    r = sync_indicators_to_biomarkers(db, u.id)

    assert r["recognized"] == 1
    assert r["skipped"] == 1                   # 让位给已有的结构化来源
    assert r["written"] == 0
    rows = _obs(db, u.id, "lipid_ldl")
    assert len(rows) == 1                       # 不写重复
    assert rows[0].source != "indicator_sync"   # 保留 exam 来源溯源


# ── ensure_biomarkers 双源 ───────────────────────────────────────────────

def test_ensure_biomarkers_merges_both_sources(db):
    from app.services.biomarker_service import ingest_exam
    from app.services.biomarker_sync import ensure_biomarkers
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    u = _mk_user(db)

    exam = MedicalExam(user_id=u.id, exam_date=datetime.date(2026, 1, 1),
                       exam_type="comprehensive", patient_gender="男", patient_age=41)
    db.add(exam); db.commit(); db.refresh(exam)
    db.add(MedicalExamItem(exam_id=exam.id, item_name="谷丙转氨酶", value=30,
                           unit="U/L", source="manual"))
    db.commit(); db.refresh(exam)
    # 注意:不先 ingest,交给 ensure 内部的 backfill_user

    # 只在 indicators 里的 LDL(不同日)
    _mk_indicator(db, u.id, "低密度脂蛋白", 3.8, "mmol/L", datetime.date(2026, 3, 1))

    r = ensure_biomarkers(db, u.id)
    assert r["exam_observations"] == 1          # backfill 体检 ALT
    assert r["written"] == 1                     # 同步 indicators LDL
    codes = {o.code for o in _obs(db, u.id)}
    assert codes == {"ALT", "lipid_ldl"}


# ── 头号修复:仅 medical_indicators 的用户 → 周期目标非空 ─────────────────

def test_metabolic_cycle_targets_from_indicators_only(db):
    """P0③ 核心:化验只进了 medical_indicators(无 MedicalExam)的用户,
    开周期前的 ensure_biomarkers 应让目标与基线非空(修复前是空目标)。"""
    from app.services.intervention_cycle_service import start_metabolic_cycle
    u = _mk_user(db)
    # 异常代谢项,仅存在于 medical_indicators
    _mk_indicator(db, u.id, "低密度脂蛋白", 3.8, "mmol/L", datetime.date(2026, 3, 1))
    _mk_indicator(db, u.id, "尿酸", 460, "µmol/L", datetime.date(2026, 3, 1))
    twin = {"meta": {"data_sources": ["labs"]}}

    cycle = start_metabolic_cycle(db, u.id, twin, days=90,
                                  start_date=datetime.date(2026, 3, 1))
    codes = {om.metric_code for om in cycle.outcomes}
    assert "lipid_ldl" in codes and "UA" in codes      # 不再是空目标
    ldl = next(om for om in cycle.outcomes if om.metric_code == "lipid_ldl")
    assert ldl.baseline_value == 3.8                    # 基线非 None
