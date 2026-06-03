"""Biomarker 归一化层测试 (Personal Health OS P1, G3)."""
import datetime
import uuid

from app.biomarkers import normalize_observation, resolve_code, get_definition


# ── 纯函数: resolve_code / normalize_observation ─────────────────────────

def test_resolve_alias_to_canonical_code():
    assert resolve_code("谷丙转氨酶") == "ALT"
    assert resolve_code("丙氨酸氨基转移酶") == "ALT"
    # exam_packages 别名表缺核心血脂中文名, 这里补齐:
    assert resolve_code("低密度脂蛋白") == "lipid_ldl"
    assert resolve_code("高密度脂蛋白") == "lipid_hdl"
    assert resolve_code("HbA1c") == "glucose_hba1c"
    assert resolve_code("不存在的项目xyz") is None


def test_alt_normal_male():
    o = normalize_observation("谷丙转氨酶", 26, "U/L", sex="male")
    assert o is not None
    assert o.code == "ALT"
    assert o.domain == "liver"
    assert o.flag == "normal"
    assert o.abnormal is False
    assert o.ref_high == 50
    assert o.confidence == "high"


def test_ldl_high_is_risk():
    o = normalize_observation("低密度脂蛋白", 3.8, "mmol/L")
    assert o.code == "lipid_ldl"
    assert o.flag == "high"
    assert o.abnormal is True
    assert o.is_risk is True


def test_ldl_unit_conversion_mgdl():
    o = normalize_observation("LDL", 150, "mg/dL")  # ≈ 3.88 mmol/L
    assert o.normalized_unit == "mmol/L"
    assert 3.7 < o.normalized_value < 4.0
    assert o.flag == "high"


def test_hdl_low_is_risk_when_higher_is_good():
    o = normalize_observation("高密度脂蛋白", 0.8, "mmol/L", sex="male")
    assert o.code == "lipid_hdl"
    assert o.flag == "low"
    assert o.abnormal is True
    assert o.is_risk is True  # HDL 偏低才是风险


def test_uric_acid_sex_specific_range():
    # 男 208–428 → 418 normal;女 155–357 → 418 high
    male = normalize_observation("尿酸", 418, "µmol/L", sex="male")
    female = normalize_observation("尿酸", 418, "µmol/L", sex="female")
    assert male.flag == "normal"
    assert female.flag == "high"
    assert female.is_risk is True


def test_hba1c_ifcc_mmol_mol_conversion():
    o = normalize_observation("HbA1c", 48, "mmol/mol")  # ≈ 6.54 %
    assert o.normalized_unit == "%"
    assert 6.3 < o.normalized_value < 6.8
    assert o.flag == "high"


def test_egfr_low_is_risk():
    o = normalize_observation("eGFR", 55, "mL/min/1.73m²")
    assert o.code == "egfr"
    assert o.flag == "low"
    assert o.is_risk is True  # eGFR 偏低为风险


def test_unknown_item_returns_none():
    assert normalize_observation("某不存在指标", 1, "x") is None


def test_unparseable_value_returns_none():
    assert normalize_observation("ALT", "阴性", "U/L") is None


def test_unknown_unit_lowers_confidence():
    o = normalize_observation("ALT", 30, "weird-unit")
    assert o is not None
    assert o.confidence == "low"


def test_definition_lookup():
    d = get_definition("低密度脂蛋白")
    assert d.code == "lipid_ldl"
    assert d.canonical_unit == "mmol/L"
    assert d.higher_is_risk is True


# ── 服务层: ingest_exam / latest_observations (DB) ───────────────────────

def _mk_user(db):
    from app.models.user import User
    u = User(
        username=f"bm_{uuid.uuid4().hex[:8]}",
        email=f"bm_{uuid.uuid4().hex[:8]}@example.com",
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


def _mk_exam(db, user_id, gender="男", age=41, items=()):
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    exam = MedicalExam(
        user_id=user_id,
        exam_date=datetime.date(2026, 5, 1),
        exam_type="comprehensive",
        patient_gender=gender,
        patient_age=age,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    for name, val, unit in items:
        db.add(MedicalExamItem(exam_id=exam.id, item_name=name, value=val, unit=unit, source="manual"))
    db.commit()
    db.refresh(exam)
    return exam


def test_ingest_exam_creates_normalized_observations(db):
    u = _mk_user(db)
    exam = _mk_exam(db, u.id, gender="男", age=41, items=[
        ("低密度脂蛋白", 3.8, "mmol/L"),
        ("谷丙转氨酶", 26, "U/L"),
        ("尿酸", 418, "µmol/L"),
        ("某不存在指标", 1.0, "x"),  # 识别不到 → 跳过
    ])
    from app.services.biomarker_service import ingest_exam, latest_observations
    obs = ingest_exam(db, exam)
    assert len(obs) == 3  # 未知项被跳过

    latest = latest_observations(db, u.id)
    assert latest["lipid_ldl"].flag == "high"
    assert latest["lipid_ldl"].is_risk is True
    assert latest["ALT"].flag == "normal"
    assert latest["UA"].flag == "normal"  # 男性 418 在范围内
    assert latest["lipid_ldl"].observed_at.date() == datetime.date(2026, 5, 1)


def test_ingest_exam_is_idempotent(db):
    u = _mk_user(db)
    exam = _mk_exam(db, u.id, items=[("低密度脂蛋白", 3.8, "mmol/L"), ("谷丙转氨酶", 26, "U/L")])
    from app.services.biomarker_service import ingest_exam
    from app.models.biomarker_observation import BiomarkerObservation
    ingest_exam(db, exam)
    ingest_exam(db, exam)  # 再跑一次不应重复
    count = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == u.id).count()
    assert count == 2


def test_observation_series_orders_by_time(db):
    u = _mk_user(db)
    from app.services.biomarker_service import ingest_exam, observation_series
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    for d, val in [(datetime.date(2026, 2, 1), 4.2), (datetime.date(2026, 5, 1), 3.8)]:
        exam = MedicalExam(user_id=u.id, exam_date=d, exam_type="lipid", patient_gender="男", patient_age=41)
        db.add(exam); db.commit(); db.refresh(exam)
        db.add(MedicalExamItem(exam_id=exam.id, item_name="低密度脂蛋白", value=val, unit="mmol/L", source="manual"))
        db.commit(); db.refresh(exam)
        ingest_exam(db, exam)
    series = observation_series(db, u.id, "lipid_ldl")
    assert [round(o.normalized_value, 1) for o in series] == [4.2, 3.8]  # 升序
