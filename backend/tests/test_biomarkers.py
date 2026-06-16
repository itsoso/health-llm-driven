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


def test_hba1c_variants_resolve_to_distinct_codes():
    # 相似名的不同指标必须分流 —— 历史上被挤进同一 code (锚点用户 user 3 实锤).
    assert resolve_code("糖化血红蛋白A1c") == "glucose_hba1c"
    assert resolve_code("HbA1c") == "glucose_hba1c"
    assert resolve_code("糖化血红蛋白A1") == "glucose_hba1_total"  # 总糖化, 参考 6.3–9.0
    assert resolve_code("HbA1") == "glucose_hba1_total"
    # bare 名按惯例 = 标准 A1c
    assert resolve_code("糖化血红蛋白") == "glucose_hba1c"


def test_hemoglobin_not_misclassified_as_hba1c():
    # 「血红蛋白」是「糖化血红蛋白」的子串 —— 旧 key-in-alias 逻辑把它误存进糖化序列.
    assert resolve_code("血红蛋白") == "hemoglobin"
    assert resolve_code("血红蛋白") != "glucose_hba1c"
    assert resolve_code("血色素") == "hemoglobin"
    assert resolve_code("HGB") == "hemoglobin"
    o = normalize_observation("血红蛋白", 160, "g/L", sex="male")
    assert o is not None
    assert o.code == "hemoglobin"
    assert o.code != "glucose_hba1c"
    assert o.flag == "normal"  # 男 130–175


def test_prefixed_name_picks_longest_substring():
    # 带前后缀的项目名 → 取最长子串别名, 不被更短子串抢走.
    assert resolve_code("血清糖化血红蛋白测定") == "glucose_hba1c"
    assert resolve_code("血清低密度脂蛋白胆固醇测定") == "lipid_ldl"


def test_resolve_drops_reverse_key_in_alias():
    # 回归: 去掉 key-in-alias 反向匹配后, 「血红蛋白」(是别名「糖化血红蛋白」的子串)
    # 不再被糖化误中 —— 这正是旧逻辑的 bug. 它现在精确命中 hemoglobin.
    assert resolve_code("血红蛋白") == "hemoglobin"
    # 「胆固醇」是「低密度脂蛋白胆固醇」「高密度脂蛋白胆固醇」的子串; 旧反向逻辑会让一个
    # 更长别名把短查询吞掉. 现在「胆固醇」是 lipid_tc 的精确别名, 稳定命中总胆固醇.
    assert resolve_code("胆固醇") == "lipid_tc"


def test_hba1c_sanity_rejects_gl_value():
    # 纵深防呆: % 指标喂 g/L / >20 的值 → None (防血红蛋白漏进糖化).
    assert normalize_observation("糖化血红蛋白", 160, "g/L") is None
    assert normalize_observation("糖化血红蛋白A1", 173, "g/L") is None
    # 即便无单位但值离谱(>20)也丢弃.
    assert normalize_observation("糖化血红蛋白", 160, None) is None
    # 合法的 % 值仍通过.
    ok = normalize_observation("糖化血红蛋白", 5.0, "%")
    assert ok is not None and ok.code == "glucose_hba1c"


def test_hba1_total_ref_range():
    o = normalize_observation("糖化血红蛋白A1", 7.0, "%")
    assert o.code == "glucose_hba1_total"
    assert o.ref_low == 6.3 and o.ref_high == 9.0
    assert o.flag == "normal"


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


# ── 消费侧防污染: 总糖化 HbA1 不得被当成标准 A1c 喂进阈值/趋势 ──────────────

def test_normalize_item_name_splits_total_hba1_from_a1c():
    """体检导入层 (api/family_health + pdf_parser 写 item_code 用的就是它).

    历史 bug: 子串「糖化血红蛋白」把「糖化血红蛋白A1」(总糖化, 参考 6.3–9.0%) 也归
    glucose_hba1c → 入库即错码, 下游趋势/阈值全错。
    """
    from app.services.exam_packages import normalize_item_name
    assert normalize_item_name("糖化血红蛋白")[0] == "glucose_hba1c"
    assert normalize_item_name("糖化血红蛋白A1c")[0] == "glucose_hba1c"
    assert normalize_item_name("HbA1c")[0] == "glucose_hba1c"
    # 总糖化必须分流
    assert normalize_item_name("糖化血红蛋白A1")[0] == "glucose_hba1_total"
    assert normalize_item_name("HbA1")[0] == "glucose_hba1_total"
    assert normalize_item_name("糖化血红蛋白A1测定")[0] == "glucose_hba1_total"


def test_fetch_latest_labs_hba1c_excludes_total_hba1(db):
    """twin.labs.hba1c 的取数源 (_collectors.fetch_latest_labs) 只认标准 A1c。

    场景: 用户化验里同时有「糖化血红蛋白A1」7.0%(总糖化, 正常) 和标准「糖化血红蛋白」5.4%。
    若取错 → twin.labs.hba1c=7.0 → SafetyGuardian 糖尿病阈值 fallback 误报 + 代谢综合征误判。
    """
    from app.models.family_health import MedicalIndicator
    from app.twin._collectors import fetch_latest_labs

    u = _mk_user(db)
    # 总糖化 A1 (更新, 名字含 hba1c 子串, 会被 ilike 误捞)
    db.add(MedicalIndicator(
        user_id=u.id, name="糖化血红蛋白A1", value=7.0, unit="%",
        record_date=datetime.date(2026, 5, 10),
    ))
    # 标准 A1c (略旧)
    db.add(MedicalIndicator(
        user_id=u.id, name="糖化血红蛋白", value=5.4, unit="%",
        record_date=datetime.date(2026, 5, 1),
    ))
    db.commit()

    labs = fetch_latest_labs(db, u.id)
    assert labs.get("hba1c") == 5.4  # 取标准 A1c, 不是更新的总糖化 7.0


def test_fetch_latest_labs_hba1c_returns_none_when_only_total(db):
    """只有总糖化 A1, 没有标准 A1c → hba1c 应为缺失, 而不是把 A1 当 A1c."""
    from app.models.family_health import MedicalIndicator
    from app.twin._collectors import fetch_latest_labs

    u = _mk_user(db)
    db.add(MedicalIndicator(
        user_id=u.id, name="糖化血红蛋白A1", value=7.0, unit="%",
        record_date=datetime.date(2026, 5, 10),
    ))
    db.commit()
    labs = fetch_latest_labs(db, u.id)
    assert "hba1c" not in labs
