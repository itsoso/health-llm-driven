"""Biomarker 归一化层测试 (Personal Health OS P1, G3)."""
import datetime
import uuid

import pytest

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
    # 未识别的单位写法只是不确定, 不是「不是该指标」的证据: 按 canonical 读, 标 low。
    # (已识别但量纲不符的单位 —— 肌酐 ml/min、血红蛋白 pg —— 才拒收, 见 test_biomarker_alias_boundaries)
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


# ── 2026-09-30 事故回归 (合成数值): exam 路径的陈旧行 / 跨 exam 重复 / 跨源重复 ──────────

def _obs(db, user_id):
    from app.models.biomarker_observation import BiomarkerObservation
    db.expire_all()
    return sorted(
        (r.code, r.normalized_value, r.source)
        for r in db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user_id)
    )


def _sync_row(db, user_id, code, value, day=datetime.date(2026, 5, 1)):
    from app.models.biomarker_observation import BiomarkerObservation
    db.add(BiomarkerObservation(
        user_id=user_id, code=code, domain="x", value=value, unit="U/L", normalized_value=value,
        normalized_unit="U/L", flag="normal", observed_at=datetime.datetime(day.year, day.month, day.day),
        source="indicator_sync",
    ))
    db.commit()


def test_ingest_exam_removes_row_whose_item_no_longer_maps(db):
    """旧映射把「极低密度脂蛋白-C」落成 lipid_ldl; 重新 ingest 必须删掉这条陈旧行, 而不是跳过不管。"""
    from app.models.biomarker_observation import BiomarkerObservation
    from app.services.biomarker_service import ingest_exam

    u = _mk_user(db)
    exam = _mk_exam(db, u.id, items=[
        ("低密度脂蛋白-C", 3.1, "mmol/L"),
        ("极低密度脂蛋白-C", 0.7, "mmol/L"),
    ])
    vldl_item = next(i for i in exam.items if i.item_name == "极低密度脂蛋白-C")
    db.add(BiomarkerObservation(
        user_id=u.id, code="lipid_ldl", domain="lipid", value=0.7, unit="mmol/L",
        normalized_value=0.7, normalized_unit="mmol/L", flag="normal",
        observed_at=datetime.datetime(2026, 5, 1), source_exam_item_id=vldl_item.id, source="manual",
    ))
    db.commit()

    ingest_exam(db, exam)

    assert _obs(db, u.id) == [("lipid_ldl", 3.1, "manual")]


def test_ingest_exam_falls_back_to_item_code_for_unrecognised_name(db):
    """名字不在别名表 (英文全称) 但带 item_code 提示 → 按提示归一, 不能整张体检零行。"""
    from app.models.medical_exam import MedicalExamItem
    from app.services.biomarker_service import ingest_exam

    u = _mk_user(db)
    exam = _mk_exam(db, u.id)
    db.add(MedicalExamItem(exam_id=exam.id, item_name="Alanine aminotransferase", item_code="ALT",
                           value=118, unit="U/L", source="manual"))
    db.add(MedicalExamItem(exam_id=exam.id, item_name="尿肌酐", item_code="CREA",  # 提示与名字冲突 → 不采信
                           value=9.4, unit="mmol/L", source="manual"))
    db.commit()
    db.refresh(exam)

    ingest_exam(db, exam)

    assert _obs(db, u.id) == [("ALT", 118, "manual")]


def test_ingest_exam_skips_identical_value_already_observed_same_day(db):
    """同一份报告被导入成两张 exam (手工 + PDF 各一次) → 同日同值只留一行。"""
    from app.services.biomarker_service import ingest_exam

    u = _mk_user(db)
    first = _mk_exam(db, u.id, items=[("谷氨酰转肽酶", 72, "U/L")])
    second = _mk_exam(db, u.id, items=[("谷氨酰转肽酶", 72, "U/L")])
    ingest_exam(db, first)
    ingest_exam(db, second)
    ingest_exam(db, second)

    assert _obs(db, u.id) == [("GGT", 72, "manual")]


def test_ingest_exam_supersedes_only_identical_sync_row(db):
    """exam 优先只针对同一次测量 (同 code、同日、同值); 同日不同值是另一次测量, 必须保留。"""
    from app.services.biomarker_service import ingest_exam

    u = _mk_user(db)
    _sync_row(db, u.id, "GGT", 72)
    _sync_row(db, u.id, "GGT", 91)
    exam = _mk_exam(db, u.id, items=[("谷氨酰转肽酶", 72, "U/L")])

    ingest_exam(db, exam)

    assert _obs(db, u.id) == [("GGT", 72, "manual"), ("GGT", 91, "indicator_sync")]


def test_same_day_reingest_restores_measurement_after_correction(db):
    """两张同日 exam 同值只留一行; 其中一张被校正后, 另一张那次测量要重新落库。"""
    from app.services.biomarker_service import ingest_exam, ingest_exam_safely

    u = _mk_user(db)
    first = _mk_exam(db, u.id, items=[("谷氨酰转肽酶", 72, "U/L")])
    second = _mk_exam(db, u.id, items=[("谷氨酰转肽酶", 72, "U/L")])
    ingest_exam(db, first)
    ingest_exam(db, second)
    first.items[0].value = 66
    db.commit()

    assert ingest_exam_safely(db, first, same_day=True) is True

    assert _obs(db, u.id) == [("GGT", 66, "manual"), ("GGT", 72, "manual")]


def test_backfill_converges_existing_duplicates_from_reimported_exam(db):
    """同一份报告录了两张 exam, 旧 backfill 给两张都落了行 → 同日同值两行。对账后只剩一行。"""
    from app.models.biomarker_observation import BiomarkerObservation
    from app.services.biomarker_service import backfill_user

    u = _mk_user(db)
    first = _mk_exam(db, u.id, items=[("谷丙转氨酶", 31, "U/L"), ("总胆固醇", 4.6, "mmol/L")])
    second = _mk_exam(db, u.id, items=[("谷丙转氨酶", 31, "U/L"), ("总胆固醇", 4.9, "mmol/L")])
    common = dict(user_id=u.id, domain="liver", value=31, unit="U/L", normalized_value=31, normalized_unit="U/L",
                  flag="normal", observed_at=datetime.datetime(2026, 5, 1), source="manual")
    for exam in (first, second):
        db.add(BiomarkerObservation(code="ALT", source_exam_item_id=exam.items[0].id, **common))
    db.commit()

    backfill_user(db, u.id)
    backfill_user(db, u.id)

    assert [(c, v) for c, v, _ in _obs(db, u.id)] == [("ALT", 31), ("lipid_tc", 4.6), ("lipid_tc", 4.9)]


# ── Twin 取数: 同日 VLDL / 被改名的尿肌酐 / MCH、MCHC 不得顶替真值; 未识别单位不回退到旧值 ──

def _mk_indicator(db, user_id, name, value, unit, d):
    from app.models.family_health import MedicalIndicator
    db.add(MedicalIndicator(user_id=user_id, name=name, value=value, unit=unit, record_date=d))
    db.commit()


def test_fetch_latest_labs_ldl_ignores_same_day_vldl(db):
    from app.twin._collectors import fetch_latest_labs

    u = _mk_user(db)
    d = datetime.date(2026, 2, 9)
    # VLDL 后插 → 同日并列时「id 最新」先碰到它
    _mk_indicator(db, u.id, "低密度脂蛋白-C", 3.1, "mmol/L", d)
    _mk_indicator(db, u.id, "极低密度脂蛋白-C", 0.7, "mmol/L", d)

    assert fetch_latest_labs(db, u.id).get("ldl") == 3.1


def test_fetch_latest_labs_creatinine_ignores_relabelled_urine_row(db):
    """尿肌酐被写入期归一化器改名为「肌酐」(unit mg/g), 日期更新 → 旧逻辑取它当血肌酐。"""
    from app.twin._collectors import fetch_latest_labs

    u = _mk_user(db)
    # 同一张体检里血肌酐与被改名的尿肌酐并列 (实际形态): 同一天内找真值
    _mk_indicator(db, u.id, "肌酐", 83, "μmol/L", datetime.date(2025, 11, 20))
    _mk_indicator(db, u.id, "肌酐", 2.4, "mg/g", datetime.date(2025, 11, 20))
    _mk_indicator(db, u.id, "肾小球滤过率(EPI-cr)", 96, "ml/min", datetime.date(2025, 11, 20))

    labs = fetch_latest_labs(db, u.id)
    assert labs.get("creatinine") == 83
    assert labs.get("egfr") == 96


def test_fetch_latest_labs_hemoglobin_rejects_relabelled_mch_and_mchc(db):
    """同一张血常规里「血红蛋白」三行 —— g/L 真值、pg (MCH)、g/L≈330 (MCHC) —— 后两者都被改名过。"""
    from app.twin._collectors import fetch_latest_labs

    u = _mk_user(db)
    _mk_indicator(db, u.id, "血红蛋白", 146, "g/L", datetime.date(2026, 2, 9))
    _mk_indicator(db, u.id, "血红蛋白", 29.8, "pg", datetime.date(2026, 2, 9))
    _mk_indicator(db, u.id, "血红蛋白", 338, "g/L", datetime.date(2026, 2, 9))

    assert fetch_latest_labs(db, u.id).get("hemoglobin") == 146


def test_fetch_latest_labs_never_skips_newest_for_an_unrecognised_unit(db):
    """最新行单位写成「-」只是不确定: 必须用它, 不能退回更旧的正常值 (陈旧值冒充现值)。"""
    from app.twin._collectors import fetch_latest_labs

    u = _mk_user(db)
    _mk_indicator(db, u.id, "LDL-C", 3.0, "mmol/L", datetime.date(2025, 6, 1))
    _mk_indicator(db, u.id, "LDL-C", 5.3, "-", datetime.date(2026, 2, 9))
    _mk_indicator(db, u.id, "eGFRcr", 27, "mL/min/1.73m2", datetime.date(2026, 2, 9))
    _mk_indicator(db, u.id, "尿酸", 455, "-", datetime.date(2026, 2, 9))
    _mk_indicator(db, u.id, "糖化血红蛋白", 53, "mmol/mol(IFCC)", datetime.date(2026, 2, 9))

    labs = fetch_latest_labs(db, u.id)
    assert labs.get("ldl") == 5.3
    assert labs.get("egfr") == 27
    assert labs.get("uric_acid") == 455
    assert labs.get("hba1c") == pytest.approx(7.0, abs=0.01)


def test_fetch_latest_labs_never_falls_back_to_an_older_value(db):
    """最新一天的值读不出 (单位量纲不符) 时是「缺失」, 不能拿更旧的正常值冒充现值。"""
    from app.twin._collectors import fetch_latest_labs

    u = _mk_user(db)
    _mk_indicator(db, u.id, "eGFR", 50, "mL/min/1.73m2", datetime.date(2026, 1, 5))
    _mk_indicator(db, u.id, "eGFR", 25, "μmol/L", datetime.date(2026, 6, 5))
    _mk_indicator(db, u.id, "糖化血红蛋白", 5.4, "%", datetime.date(2026, 1, 5))
    _mk_indicator(db, u.id, "糖化血红蛋白", 7.4, "mmol/L", datetime.date(2026, 6, 5))
    _mk_indicator(db, u.id, "肌酐", 70, "μmol/L", datetime.date(2026, 1, 5))
    _mk_indicator(db, u.id, "肌酐", 1.6, None, datetime.date(2026, 6, 5))  # 缺单位的 mg/dL: 能读出

    labs = fetch_latest_labs(db, u.id)
    assert "egfr" not in labs
    assert "hba1c" not in labs
    assert labs.get("creatinine") == pytest.approx(141.44)


def test_fetch_latest_labs_fasting_glucose_ignores_timed_and_urine_glucose(db):
    from app.models.family_health import MedicalIndicator
    from app.twin._collectors import fetch_latest_labs

    u = _mk_user(db)
    _mk_indicator(db, u.id, "空腹血糖", 5.0, "mmol/L", datetime.date(2026, 1, 5))
    _mk_indicator(db, u.id, "GLU-1h", 10.5, "mmol/L", datetime.date(2026, 6, 5))
    db.add(MedicalIndicator(user_id=u.id, name="葡萄糖(60min)", item_code="GLU", value=10.5, unit="mmol/L",
                            record_date=datetime.date(2026, 6, 6)))
    db.add(MedicalIndicator(user_id=u.id, name="葡萄糖(尿)", name_en="GLU", value=14.0, unit="mmol/L",
                            record_date=datetime.date(2026, 6, 7)))
    db.commit()

    assert fetch_latest_labs(db, u.id).get("blood_glucose") == 5.0


def test_latest_reading_keeps_undated_rows_in_newest_group():
    """无日期行 (合成 twin / 旧缓存) 并入最新组取最差值, 绝不因缺日期被丢 (与 lab_pick.pick_worst 一致)。"""
    from app.biomarkers.normalize import latest_reading

    rows = [
        ("2026-05-11", "低密度脂蛋白-C", 2.4, "mmol/L", "dated"),
        ("", "LDL-C", 5.1, "mmol/L", "undated"),
        ("2025-01-02", "低密度脂蛋白-C", 6.0, "mmol/L", "older"),
    ]
    assert latest_reading(rows, "lipid_ldl", pick=max) == ("undated", 5.1)
    assert latest_reading([rows[1]], "lipid_ldl", pick=max) == ("undated", 5.1)
