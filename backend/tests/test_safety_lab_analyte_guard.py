"""Safety 化验 analyte 身份守卫回归 (2026-09-30 safety review)。

背景: labs 规则与 fetch_latest_labs 用关键字子串认 analyte, pick_worst 取最差值后会稳定选中
**错误 analyte** (EGFR 基因突变丰度 / IFCC HbA1c / 尿酸碱度 / 氧化 LDL / Gastrin …) → 假告警。

不变量(加层不减层):
  - 排除只删**可证明不是该 analyte** 的行; 真实 analyte (各种写法) 必须仍告警 —— 正例同批覆盖。
  - 被排除/不可信的行不算「已覆盖」, 落到 uncategorized 兜底, 绝不静默丢。
"""

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.schema import Severity
from app.twin.schema import HealthTwin, LabsContext, TwinMeta

DAY = date.today() - timedelta(days=3)


def _item(name, value, unit=None, day=DAY):
    return {"item_name": name, "value": value, "unit": unit, "exam_date": day}


def _twin(flagged, **labs):
    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    twin.labs = LabsContext(flagged_abnormal=flagged, **labs)
    return twin


def _alerts(twin):
    return {a.rule_id: a for a in evaluate_safety(twin).alerts}


def _uncategorized(alerts):
    a = alerts.get("labs.uncategorized_abnormal")
    return a.data_citation["uncategorized_items"] if a else []


def _assert_needs_review(alerts, name, *silent_rules):
    """声明单位与量级矛盾 = 读不出 (#259 canonical 语义): 专项规则不按猜测的单位出结论, 也不退回旧值;
    兜底升级为 MEDIUM「需核对」+ requires_medical_attention, 该行列在 needs_review_items。"""
    for rule in silent_rules:
        assert rule not in alerts
    a = alerts["labs.uncategorized_abnormal"]
    assert a.severity == Severity.MEDIUM and a.requires_medical_attention
    assert name in a.data_citation["needs_review_items"]


# ─────────────────────── eGFR ───────────────────────


class TestEgfrIdentity:
    def test_egfr_gene_mutation_abundance_not_kidney(self):
        alerts = _alerts(_twin([_item("EGFR基因突变丰度", 2.1, "%")]))
        assert "labs.egfr_decline" not in alerts
        assert "EGFR基因突变丰度" in _uncategorized(alerts)

    def test_egfr_exon_mutation_english_not_kidney(self):
        alerts = _alerts(_twin([_item("EGFR exon 19 deletion", 12.0)]))
        assert "labs.egfr_decline" not in alerts

    def test_resolve_code_rejects_gene_mutation(self):
        from app.biomarkers.definitions import resolve_code

        assert resolve_code("EGFR基因突变丰度") is None
        assert resolve_code("eGFR(CKD-EPI)") == "egfr"

    @pytest.mark.parametrize("bad", [0.0, -3.0, 250.0, 900.0])
    def test_implausible_canonical_egfr_ignored(self, bad):
        assert "labs.egfr_decline" not in _alerts(_twin([], egfr=bad))

    def test_flagged_egfr_below_one_read_as_ml_per_s(self):
        # 原始化验行 <1 mL/min 物理不可能, 只可能是 mL/s: 0.5 → 30 → 告警(不因「不可信」丢掉)
        assert _alerts(_twin([_item("eGFR", 0.5)]))["labs.egfr_decline"].data_citation["egfr"] == 30.0

    @pytest.mark.parametrize("name", [
        "eGFR(CKD-EPI)", "估算肾小球滤过率", "EGFR", "eGFR", "eGFRcr", "eGFRcr-cys", "eGFRcys",
        "eGFR-EPI", "GFR", "估算GFR",
    ])
    def test_real_egfr_still_alerts(self, name):
        a = _alerts(_twin([_item(name, 25.0, "mL/min/1.73m²")]))["labs.egfr_decline"]
        assert a.severity == Severity.HIGH

    def test_real_egfr_wins_over_same_day_mutation_row(self):
        a = _alerts(_twin([
            _item("EGFR基因突变丰度", 2.1, "%"), _item("eGFR(CKD-EPI)", 40.0),
        ]))["labs.egfr_decline"]
        assert a.data_citation["egfr"] == 40.0

    def test_egfr_ml_per_s_converted(self):
        # 北欧单位 mL/s/1.73m²: 0.4 mL/s ≈ 24 mL/min → HIGH
        a = _alerts(_twin([_item("eGFR", 0.4, "mL/s/1.73m²")]))["labs.egfr_decline"]
        assert a.data_citation["egfr"] == pytest.approx(24.0)

    def test_canonical_egfr_fallback_still_alerts(self):
        assert _alerts(_twin([], egfr=25.0))["labs.egfr_decline"].severity == Severity.HIGH


# ─────────────────────── HbA1c ───────────────────────


class TestHba1cIdentity:
    def test_ifcc_mmol_mol_converted_not_read_as_percent(self):
        a = _alerts(_twin([_item("HbA1c", 42, "mmol/mol")]))
        assert "labs.hba1c_diabetes" not in a
        # 42 mmol/mol ≈ 5.99% → 糖尿病前期, 换算后仍告警 (不漏)
        assert a["labs.hba1c_prediabetes"].data_citation["hba1c"] == pytest.approx(5.99, abs=0.02)

    def test_ifcc_diabetes_range_still_high(self):
        a = _alerts(_twin([_item("糖化血红蛋白(IFCC)", 58, "mmol/mol")]))
        assert a["labs.hba1c_diabetes"].severity == Severity.HIGH

    def test_unitless_ifcc_magnitude_inferred(self):
        # OCR 缺单位常见: 42 不可能是 %, 按 IFCC 推断 ≈5.99% → 前期; 53 ≈ 7.0% → 糖尿病
        a = _alerts(_twin([_item("HbA1c", 42)]))
        assert "labs.hba1c_diabetes" not in a
        assert a["labs.hba1c_prediabetes"].data_citation["hba1c"] == pytest.approx(5.99, abs=0.02)
        assert _alerts(_twin([_item("HbA1c", 53)]))["labs.hba1c_diabetes"].severity == Severity.HIGH

    @pytest.mark.parametrize("name", ["糖化血红蛋白(IFCC标准化)", "HbA1c (NGSP/IFCC)"])
    def test_ifcc_in_name_but_percent_unit_not_converted(self, name):
        a = _alerts(_twin([_item(name, 6.8, "%")]))["labs.hba1c_diabetes"]
        assert a.data_citation["hba1c"] == 6.8

    def test_impossible_value_surfaced_not_alerted(self):
        alerts = _alerts(_twin([_item("HbA1c", 250)]))
        assert "labs.hba1c_diabetes" not in alerts
        assert "HbA1c" in _uncategorized(alerts)

    def test_implausible_canonical_hba1c_ignored(self):
        assert "labs.hba1c_diabetes" not in _alerts(_twin([], hba1c=42.0))

    @pytest.mark.parametrize("name", ["Hemoglobin A1c", "糖化血红蛋白", "HbA1c"])
    def test_real_hba1c_still_alerts(self, name):
        a = _alerts(_twin([_item(name, 7.2, "%")]))["labs.hba1c_diabetes"]
        assert a.severity == Severity.HIGH


# ─────────────────────── 尿酸 ───────────────────────


class TestUricAcidIdentity:
    @pytest.mark.parametrize("name,value", [
        ("尿酸碱度", 8.0),
        ("尿尿酸", 4200.0),
        ("24h尿尿酸", 4200.0),
        ("尿酸/肌酐比值", 0.6),
        ("尿酸/肌酐", 0.6),
        ("UA-PH", 8.0),
        ("UA, pH", 8.0),
        ("UA Glucose", 8.0),
    ])
    def test_not_serum_uric_acid(self, name, value):
        alerts = _alerts(_twin([_item(name, value)]))
        assert "labs.uric_acid_high" not in alerts
        assert name in _uncategorized(alerts)

    @pytest.mark.parametrize("name,value", [
        ("尿酸", 520.0), ("血尿酸", 520.0), ("尿酸(UA/URIC)", 520.0), ("Uric Acid", 8.8),
        ("血清尿酸", 520.0), ("UA(尿酸)", 520.0), ("UA", 520.0), ("SUA", 520.0),
        ("血尿酸", 1600.0),  # 肿瘤溶解可 >1500 μmol/L
    ])
    def test_real_serum_uric_acid_still_alerts(self, name, value):
        assert _alerts(_twin([_item(name, value)]))["labs.uric_acid_high"].severity == Severity.MEDIUM


# ─────────────────────── LDL ───────────────────────


class TestLdlIdentity:
    @pytest.mark.parametrize("name,value", [
        ("氧化低密度脂蛋白", 80.0),
        ("Ox-LDL", 80.0),
        ("极低密度脂蛋白胆固醇", 5.2),
        ("VLDL-C", 5.2),
        ("LDL-C/HDL-C", 5.0),
    ])
    def test_not_ldl_c(self, name, value):
        alerts = _alerts(_twin([_item(name, value)]))
        assert "labs.ldl_high" not in alerts
        assert name in _uncategorized(alerts)

    def test_unitless_mg_dl_magnitude_inferred(self):
        assert "labs.ldl_high" not in _alerts(_twin([_item("LDL-C", 80.0)]))  # 2.07 mmol/L
        a = _alerts(_twin([_item("LDL-C", 200.0)]))["labs.ldl_high"]
        assert a.data_citation["ldl"] == pytest.approx(5.17, abs=0.02)

    def test_homozygous_fh_extreme_ldl_kept(self):
        a = _alerts(_twin([_item("LDL-C", 18.0, "mmol/L")]))["labs.ldl_high"]
        assert a.data_citation["ldl"] == 18.0

    def test_ldl_mg_dl_converted(self):
        a = _alerts(_twin([_item("LDL-C", 200.0, "mg/dL")]))["labs.ldl_high"]
        assert a.severity == Severity.HIGH
        assert a.data_citation["ldl"] == pytest.approx(5.17, abs=0.02)

    def test_implausible_canonical_ldl_ignored(self):
        assert "labs.ldl_high" not in _alerts(_twin([], ldl=80.0))

    @pytest.mark.parametrize("name", [
        "低密度脂蛋白胆固醇", "LDL-C", "低密度脂蛋白胆固醇(LDL-C)", "LDLC", "LDLcalc", "DLDL",
        "LDL-C(直接法)",
    ])
    def test_real_ldl_still_alerts(self, name):
        assert _alerts(_twin([_item(name, 5.2, "mmol/L")]))["labs.ldl_high"].severity == Severity.HIGH


# ─────────────────────── 肝酶 ───────────────────────


class TestLiverIdentity:
    @pytest.mark.parametrize("name", ["Gastrin", "Fasting glucose", "Blast cells"])
    def test_english_words_containing_ast_not_ast(self, name):
        alerts = _alerts(_twin([_item("ALT", 250.0), _item(name, 300.0)]))
        assert "labs.liver_enzyme_pattern" not in alerts

    @pytest.mark.parametrize("alt_name,ast_name", [
        ("丙氨酸氨基转移酶(ALT/GPT)", "天门冬氨酸氨基转移酶(AST/GOT)"),
        ("ALT", "AST"),
        ("谷丙转氨酶", "谷草转氨酶"),
        ("ALT谷丙转氨酶", "AST谷草转氨酶"),
        ("ALT(GPT)", "AST(SGOT)"),
        ("SGPT", "SGOT"),
        ("丙氨酸转氨酶", "天冬氨酸转氨酶"),
    ])
    def test_real_liver_enzymes_still_alert(self, alt_name, ast_name):
        a = _alerts(_twin([_item(alt_name, 250.0), _item(ast_name, 210.0)]))
        assert a["labs.liver_enzyme_pattern"].severity == Severity.CRITICAL

    @pytest.mark.parametrize("ratio", ["AST/ALT比值", "AST/ALT", "GOT/GPT", "谷草/谷丙"])
    def test_ast_alt_ratio_not_an_enzyme(self, ratio):
        alerts = _alerts(_twin([_item("ALT", 100.0), _item(ratio, 2.5)]))
        assert "labs.liver_enzyme_pattern" not in alerts
        assert ratio in _uncategorized(alerts)

    def test_ggtp_counts_as_ggt(self):
        a = _alerts(_twin([_item("ALT", 250.0), _item("GGTP", 300.0)]))
        assert a["labs.liver_enzyme_pattern"].severity == Severity.CRITICAL


# ─────────────────────── creatinine citation ───────────────────────


class TestCreatinineCitation:
    @pytest.mark.parametrize("decoy", [
        ("CRP", 50.0), ("尿酸/肌酐", 0.6), ("hs-CRP", 12.0), ("铬(Cr)", 3.0), ("肌酐清除率", 60.0),
    ])
    def test_citation_ignores_crp_and_ratios(self, decoy):
        a = _alerts(_twin([_item(*decoy), _item("eGFR", 40.0)]))["labs.egfr_decline"]
        assert a.data_citation["creatinine"] is None

    @pytest.mark.parametrize("name", ["肌酐", "Cr", "血肌酐(Cr)", "Creatinine", "Cre", "SCr", "CREA"])
    def test_citation_uses_real_creatinine(self, name):
        a = _alerts(_twin([_item("CRP", 50.0), _item(name, 180.0), _item("eGFR", 40.0)]))
        assert a["labs.egfr_decline"].data_citation["creatinine"] == 180.0


# ─────────────────────── collector: fetch_latest_labs ───────────────────────


def _user(db):
    from app.models.user import User

    user = User(
        username=f"ag_{uuid.uuid4().hex[:6]}", email=f"ag_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x", name="analyte guard", birth_date=date(1980, 1, 1),
        gender="男", is_active=True, is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add(db, user_id, name, value, *, unit=None, day=DAY, name_en=None, item_code=None):
    from app.models.family_health import MedicalIndicator

    row = MedicalIndicator(
        user_id=user_id, name=name, value=value, unit=unit, record_date=day,
        name_en=name_en, item_code=item_code, is_abnormal=False, source="pdf_import",
    )
    db.add(row)
    db.flush()
    return row


class TestFetchLatestLabsIdentity:
    def test_wrong_analytes_never_become_canonical(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        older = DAY - timedelta(days=30)
        _add(db, user.id, "估算肾小球滤过率", 48.0, day=older)
        _add(db, user.id, "低密度脂蛋白胆固醇", 3.1, unit="mmol/L", day=older)
        _add(db, user.id, "血尿酸", 380.0, day=older)
        _add(db, user.id, "糖化血红蛋白", 5.9, unit="%", day=older)
        _add(db, user.id, "谷草转氨酶", 30.0, day=older)
        # 更新但错误的 analyte —— 旧 first() 会选中它们
        _add(db, user.id, "EGFR基因突变丰度", 2.1, unit="%")
        _add(db, user.id, "氧化低密度脂蛋白", 80.0)
        _add(db, user.id, "尿酸碱度", 8.0)
        _add(db, user.id, "HbA1c", 42.0)
        _add(db, user.id, "Gastrin", 300.0)
        db.commit()

        out = fetch_latest_labs(db, user.id)
        assert out["egfr"] == 48.0
        assert out["ldl"] == 3.1
        assert out["uric_acid"] == 380.0
        # 无单位 42 按 IFCC 量级推断(≈5.99%), 绝不当 42%
        assert out["hba1c"] == pytest.approx(5.99, abs=0.02)
        assert out["ast"] == 30.0

    def test_real_analytes_and_units_normalized(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "eGFR(CKD-EPI)", 42.0)
        _add(db, user.id, "LDL-C", 200.0, unit="mg/dL")
        _add(db, user.id, "Hemoglobin A1c", 53.0, unit="mmol/mol")
        _add(db, user.id, "尿酸(UA/URIC)", 520.0)
        _add(db, user.id, "丙氨酸氨基转移酶(ALT/GPT)", 120.0)
        _add(db, user.id, "尿常规", 8.0, name_en="UA-PH")
        db.commit()

        out = fetch_latest_labs(db, user.id)
        assert out["egfr"] == 42.0
        assert out["ldl"] == pytest.approx(5.17, abs=0.02)
        assert out["hba1c"] == pytest.approx(7.0, abs=0.02)
        assert out["uric_acid"] == 520.0
        assert out["alt"] == 120.0

    def test_english_suffix_forms_and_exact_ua_code(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "eGFRcr-cys", 38.0)
        _add(db, user.id, "LDLC", 5.5, unit="mmol/L")
        _add(db, user.id, "UA", 450.0, item_code="UA")
        db.commit()
        out = fetch_latest_labs(db, user.id)
        assert out["egfr"] == 38.0
        assert out["ldl"] == 5.5
        assert out["uric_acid"] == 450.0

    def test_same_day_tie_is_deterministic_newest_id(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "估算肾小球滤过率", 70.0)
        _add(db, user.id, "估算肾小球滤过率", 45.0)  # 更大 id 的同日行
        db.commit()
        assert fetch_latest_labs(db, user.id)["egfr"] == 45.0


# ─────────────────────── review round 2 repros ───────────────────────

OLD_DAY = DAY - timedelta(days=200)


class TestRound2WordBoundaries:
    @pytest.mark.parametrize("name,value,rule", [
        ("eGFR (Estimated Glomerular Filtration Rate)", 25.0, "labs.egfr_decline"),
        ("eGFRcreat", 25.0, "labs.egfr_decline"),
        ("eGFREPI", 25.0, "labs.egfr_decline"),
        ("Uric Acid concentration", 520.0, "labs.uric_acid_high"),
        ("UricAcid", 8.5, "labs.uric_acid_high"),
        ("LDL-C concentration", 5.2, "labs.ldl_high"),
        ("LDLD", 5.2, "labs.ldl_high"),
        ("HbA1c DCCT-calibration", 7.2, "labs.hba1c_diabetes"),
    ])
    def test_real_analyte_with_english_words_alerts(self, name, value, rule):
        assert rule in _alerts(_twin([_item(name, value)]))

    def test_liver_names_with_concentration(self):
        a = _alerts(_twin([_item("ALT concentration", 250.0), _item("AST concentration", 210.0)]))
        assert a["labs.liver_enzyme_pattern"].severity == Severity.CRITICAL

    def test_creat_citation(self):
        a = _alerts(_twin([_item("CREAT", 200.0), _item("eGFR", 40.0)]))
        assert a["labs.egfr_decline"].data_citation["creatinine"] == 200.0

    @pytest.mark.parametrize("items,rule", [
        ([("EGFR 19del", 12.0, "%")], "labs.egfr_decline"),
        ([("EGFRvIII", 30.0, None)], "labs.egfr_decline"),
        ([("ALT", 250.0, None), ("GOT2", 300.0, None)], "labs.liver_enzyme_pattern"),
        ([("AST", 250.0, None), ("GPT2", 300.0, None)], "labs.liver_enzyme_pattern"),
        ([("LDLR", 8.0, None)], "labs.ldl_high"),
    ])
    def test_gene_symbols_not_analytes(self, items, rule):
        assert rule not in _alerts(_twin([_item(*i) for i in items]))


class TestRound2NoStaleFallback:
    def test_low_real_ldl_today_not_replaced_by_old_exam(self):
        a = _alerts(_twin([_item("LDL-C", 0.25, "mmol/L"), _item("LDL-C", 4.5, "mmol/L", day=OLD_DAY)]))
        assert "labs.ldl_high" not in a

    def test_low_real_hba1c_today_not_replaced_by_old_exam(self):
        a = _alerts(_twin([_item("糖化血红蛋白", 2.8, "%"), _item("糖化血红蛋白", 7.2, "%", day=OLD_DAY)]))
        assert "labs.hba1c_diabetes" not in a

    def test_impossible_latest_blocks_older_and_surfaces(self):
        a = _alerts(_twin([_item("LDL-C", 5000.0, "mmol/L"), _item("LDL-C", 4.5, "mmol/L", day=OLD_DAY)]))
        assert "labs.ldl_high" not in a
        assert "LDL-C" in _uncategorized(a)

    def test_impossible_latest_does_not_use_canonical_either_way(self):
        # 同日另有可信值时仍用它
        a = _alerts(_twin([_item("LDL-C", 5000.0), _item("低密度脂蛋白胆固醇", 5.2, "mmol/L")]))
        assert a["labs.ldl_high"].data_citation["ldl"] == 5.2


class TestRound2UnitContradiction:
    """声明单位与量级矛盾 (OCR 单位错位): 不按声明单位硬换算成假「正常值」(6.8 mmol/mol → 2.77%、
    LDL 5.2 mg/dL → 0.13), 也不猜另一种单位 —— 升级「需核对」(与 #259 canonical 层同一语义)。"""

    @pytest.mark.parametrize("name,value,unit,rules", [
        ("HbA1c", 6.8, "mmol/mol", ("labs.hba1c_diabetes", "labs.hba1c_prediabetes")),
        ("HbA1c", 42, "%", ("labs.hba1c_diabetes", "labs.hba1c_prediabetes")),
        ("LDL-C", 160.0, "mmol/L", ("labs.ldl_high",)),
        ("LDL-C", 5.2, "mg/dL", ("labs.ldl_high",)),
    ])
    def test_declared_unit_contradiction_needs_review(self, name, value, unit, rules):
        _assert_needs_review(_alerts(_twin([_item(name, value, unit)])), name, *rules)

    def test_unitless_egfr_below_one_is_ml_per_s(self):
        a = _alerts(_twin([_item("eGFR", 0.7)]))["labs.egfr_decline"]
        assert a.data_citation["egfr"] == pytest.approx(42.0)

    def test_unitless_low_egfr_kept_as_ml_min(self):
        # 2 可能是 ESRD 的 mL/min, 也可能是 mL/s; 取会告警的解读(绝不漏报)
        assert _alerts(_twin([_item("eGFR", 2.0)]))["labs.egfr_decline"].severity == Severity.HIGH


class TestRound2Collector:
    def test_name_en_with_filtration_rate_does_not_veto(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "肾小球滤过率", 45.0, name_en="Glomerular Filtration Rate")
        db.commit()
        assert fetch_latest_labs(db, user.id)["egfr"] == 45.0

    def test_low_real_value_today_not_replaced_by_old(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "LDL-C", 4.5, unit="mmol/L", day=OLD_DAY)
        _add(db, user.id, "LDL-C", 0.25, unit="mmol/L")
        _add(db, user.id, "糖化血红蛋白", 7.2, unit="%", day=OLD_DAY)
        _add(db, user.id, "糖化血红蛋白", 2.8, unit="%")
        _add(db, user.id, "eGFR", 80.0, day=OLD_DAY)
        _add(db, user.id, "eGFR", 0.8)
        db.commit()
        out = fetch_latest_labs(db, user.id)
        assert out["ldl"] == 0.25
        assert out["hba1c"] == 2.8
        assert out["egfr"] == pytest.approx(48.0)

    def test_impossible_latest_yields_no_value_not_stale(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "LDL-C", 4.5, unit="mmol/L", day=OLD_DAY)
        _add(db, user.id, "LDL-C", 5000.0, unit="mmol/L")
        db.commit()
        assert "ldl" not in fetch_latest_labs(db, user.id)

    def test_many_newer_prefilter_decoys_do_not_hide_real_value(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "尿酸", 380.0, day=OLD_DAY)
        for i in range(150):
            _add(db, user.id, f"UA-X{i}", 1.0)
        db.commit()
        assert fetch_latest_labs(db, user.id)["uric_acid"] == 380.0


# ─────────────────────── review round 3 repros ───────────────────────


class TestRound3LegacyMiscodedHba1c:
    """b22d9c737 之前 normalize_item_name 把总糖化「糖化血红蛋白A1」与「血红蛋白」编成
    glucose_hba1c, family_health 写 name_en = item_code = code; 存量行未迁移。"""

    def test_total_hba1_coded_as_a1c_not_used(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "糖化血红蛋白", 5.0, unit="%")
        _add(db, user.id, "糖化血红蛋白A1", 6.8, unit="%", name_en="glucose_hba1c", item_code="glucose_hba1c")
        db.commit()
        assert fetch_latest_labs(db, user.id)["hba1c"] == 5.0

    def test_hemoglobin_coded_as_a1c_not_used(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "糖化血红蛋白", 5.2, unit="%", day=OLD_DAY)
        _add(db, user.id, "血红蛋白", 173.0, unit="g/L", name_en="glucose_hba1c", item_code="glucose_hba1c")
        db.commit()
        assert fetch_latest_labs(db, user.id)["hba1c"] == 5.2

    def test_only_hemoglobin_coded_as_a1c_gives_nothing(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "血红蛋白", 160.0, unit="g/L", name_en="glucose_hba1c", item_code="glucose_hba1c")
        db.commit()
        assert "hba1c" not in fetch_latest_labs(db, user.id)

    def test_english_display_name_with_code_still_used(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "Hemoglobin A1c", 7.1, unit="%", name_en="glucose_hba1c", item_code="glucose_hba1c")
        db.commit()
        assert fetch_latest_labs(db, user.id)["hba1c"] == 7.1

    # mmol/L 不在此列: A1c 名 + mmol/L 按量级解读(见 TestRound4UnitNeverVetoesIdentity)
    @pytest.mark.parametrize("unit", ["g/L", "g/dL"])
    def test_hemoglobin_units_never_hba1c(self, unit):
        alerts = _alerts(_twin([_item("糖化血红蛋白", 60.0, unit)]))
        assert "labs.hba1c_diabetes" not in alerts
        assert "labs.hba1c_prediabetes" not in alerts
        assert "糖化血红蛋白" in _uncategorized(alerts)


class TestRound3NonBlocking:
    def test_very_low_ldl_mmol_kept(self):
        # PCSK9 + 他汀下 mmol/L 极低值是真实读数, 不判不可信
        a = _alerts(_twin([_item("LDL-C", 0.1, "mmol/L"), _item("LDL-C", 4.5, "mmol/L", day=OLD_DAY)]))
        assert "labs.ldl_high" not in a
        assert "LDL-C" not in _uncategorized(a)

    def test_canonical_twin_values_not_reinterpreted(self):
        # collector 已换算到规则单位; 不再二次按 mg/dL 重读
        assert "labs.ldl_high" not in _alerts(_twin([], ldl=31.0))
        assert "labs.egfr_decline" not in _alerts(_twin([], egfr=0.5))
        assert _alerts(_twin([], ldl=18.0))["labs.ldl_high"].data_citation["ldl"] == 18.0

    @pytest.mark.parametrize("name", ["EGFR拷贝数", "EGFR蛋白表达", "EGFR IHC", "EGFR FISH", "EGFR copy number"])
    def test_egfr_gene_protein_assays_not_kidney(self, name):
        alerts = _alerts(_twin([_item(name, 3.0)]))
        assert "labs.egfr_decline" not in alerts
        assert name in _uncategorized(alerts)

    @pytest.mark.parametrize("name", ["尿白蛋白肌酐比", "尿蛋白肌酐比", "UACR", "UPCR"])
    def test_urine_ratios_not_creatinine(self, name):
        alerts = _alerts(_twin([_item(name, 30.0), _item("eGFR", 40.0)]))
        assert alerts["labs.egfr_decline"].data_citation["creatinine"] is None
        assert name in _uncategorized(alerts)

    @pytest.mark.parametrize("name", ["LDL-TG", "低密度脂蛋白甘油三酯"])
    def test_ldl_triglycerides_not_ldl_c(self, name):
        assert "labs.ldl_high" not in _alerts(_twin([_item(name, 5.2)]))


# ─────────────────────── review round 4 repros ───────────────────────


class TestRound4UnitNeverVetoesIdentity:
    """名称就是 A1c 的行, 单位不对 (mmol/L、g/L) 时它仍是最新一次 A1c: 读不出 → 需核对 / collector 缺失,
    绝不当成「别的指标」跳过而让更旧的检查冒充当前。"""

    @pytest.mark.parametrize("name,value", [("HbA1c", 52.0), ("糖化血红蛋白", 6.9)])
    def test_collector_a1c_with_mmol_l_unit_blocks_older(self, db, name, value):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, name, 5.4, unit="%", day=OLD_DAY)
        _add(db, user.id, name, value, unit="mmol/L")
        db.commit()
        assert "hba1c" not in fetch_latest_labs(db, user.id)

    def test_rule_a1c_with_mmol_l_unit_today_blocks_older(self):
        a = _alerts(_twin([_item("HbA1c", 52.0, "mmol/L"), _item("HbA1c", 6.0, "%", day=OLD_DAY)]))
        _assert_needs_review(a, "HbA1c", "labs.hba1c_diabetes", "labs.hba1c_prediabetes")

    def test_a1c_named_row_with_g_l_blocks_older_value(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "糖化血红蛋白", 5.4, unit="%", day=OLD_DAY)
        _add(db, user.id, "糖化血红蛋白", 60.0, unit="g/L")
        db.commit()
        assert "hba1c" not in fetch_latest_labs(db, user.id)

    def test_rule_a1c_named_row_with_g_l_blocks_older_value(self):
        a = _alerts(_twin([_item("糖化血红蛋白", 60.0, "g/L"), _item("糖化血红蛋白", 7.2, "%", day=OLD_DAY)]))
        assert "labs.hba1c_diabetes" not in a
        assert "糖化血红蛋白" in _uncategorized(a)


class TestRound4NarrowExclusions:
    def test_ldl_with_tg_condition_in_name_is_ldl(self):
        a = _alerts(_twin([_item("LDL-C(TG<4.5)", 5.2, "mmol/L"), _item("LDL-C", 3.5, "mmol/L", day=OLD_DAY)]))
        assert a["labs.ldl_high"].data_citation["ldl"] == 5.2

    def test_egfr_formula_expression_is_egfr(self):
        assert "labs.egfr_decline" in _alerts(_twin([_item("eGFR (表达式计算)", 25.0)]))

    def test_ldl_below_10_mg_dl_needs_review(self):
        # <10 "mg/dL" 与 mmol/L 写错单位无法区分: 不当 0.21 (假安心), 也不猜 8 mmol/L → 需核对
        _assert_needs_review(_alerts(_twin([_item("LDL-C", 8.0, "mg/dL")])), "LDL-C", "labs.ldl_high")


# ─────────────────────── review round 5 repros ───────────────────────


class TestRound5ReinterpretedRowsNeverVanish:
    """声明单位与量级矛盾而改读另一单位的行: 规则可用换算值, 但若专项规则不触发,
    该实验室已标异常的行必须进 uncategorized, 绝不零痕迹; collector 不把改读值当当前值。"""

    @pytest.mark.parametrize("name,value,unit", [
        ("HbA1c", 21.0, "%"), ("HbA1c", 38.0, "%"), ("LDL-C", 100.0, "mmol/L"),
    ])
    def test_reinterpreted_normal_value_surfaces(self, name, value, unit):
        a = _alerts(_twin([_item(name, value, unit)]))
        assert name in _uncategorized(a)

    def test_reinterpreted_row_today_still_blocks_older_and_surfaces(self):
        a = _alerts(_twin([_item("HbA1c", 21.0, "%"), _item("HbA1c", 7.5, "%", day=OLD_DAY)]))
        assert "labs.hba1c_diabetes" not in a  # 旧值不冒充当前
        assert "HbA1c" in _uncategorized(a)

    def test_unit_contradiction_row_is_never_silently_covered(self):
        a = _alerts(_twin([_item("HbA1c", 6.8, "mmol/mol")]))
        _assert_needs_review(a, "HbA1c", "labs.hba1c_diabetes")

    def test_collector_declared_unit_contradiction_gives_no_value(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "HbA1c", 7.5, unit="%", day=OLD_DAY)
        _add(db, user.id, "HbA1c", 21.0, unit="%")
        _add(db, user.id, "LDL-C", 4.5, unit="mmol/L", day=OLD_DAY)
        _add(db, user.id, "LDL-C", 100.0, unit="mmol/L")
        db.commit()
        out = fetch_latest_labs(db, user.id)
        assert "hba1c" not in out
        assert "ldl" not in out


class TestRound5VetoedLatestRowStopsCollector:
    def test_egfr_percent_latest_blocks_older(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "eGFR", 90.0, unit="mL/min/1.73m²", day=OLD_DAY)
        _add(db, user.id, "eGFR", 45.0, unit="%", item_code="egfr")
        db.commit()
        assert "egfr" not in fetch_latest_labs(db, user.id)

    def test_egfr_percent_flagged_surfaces(self):
        a = _alerts(_twin([_item("eGFR", 45.0, "%")]))
        assert "eGFR" in _uncategorized(a)

    def test_hints_never_veto_display_name(self, db):
        # name_en/item_code 只能补认不能否决: 存量行的 code 由旧版 normalize_item_name 从名字派生,
        # 曾把「肾小球滤过率(EPI-cr)」编成 CREA —— 让它否决会把真 eGFR 挡掉 (漏报)。显示名为准。
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "糖化血红蛋白", 5.4, unit="%", day=OLD_DAY)
        _add(db, user.id, "糖化血红蛋白", 6.9, unit="%", name_en="HbA1")
        _add(db, user.id, "肾小球滤过率(EPI-cr)", 42.0, name_en="CREA", item_code="CREA")
        db.commit()
        out = fetch_latest_labs(db, user.id)
        assert out["hba1c"] == 6.9
        assert out["egfr"] == 42.0

    def test_other_analyte_latest_still_skipped(self, db):
        # 最新行可证明是别的指标(尿尿酸) → 跳过, 取血尿酸(本就是最新血尿酸)
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "血尿酸", 380.0, day=OLD_DAY)
        _add(db, user.id, "尿尿酸", 4200.0)
        db.commit()
        assert fetch_latest_labs(db, user.id)["uric_acid"] == 380.0


class TestRound5NonBlocking:
    @pytest.mark.parametrize("name", ["UA(酶法)", "血清UA", "S-UA"])
    def test_ua_variants_are_uric_acid(self, name):
        assert _alerts(_twin([_item(name, 520.0)]))["labs.uric_acid_high"].severity == Severity.MEDIUM

    @pytest.mark.parametrize("name", ["糖化白蛋白", "Glycated albumin"])
    def test_glycated_albumin_not_hba1c(self, name):
        alerts = _alerts(_twin([_item(name, 18.0, "%")]))
        assert "labs.hba1c_diabetes" not in alerts
        assert name in _uncategorized(alerts)


# ─────────────────────── review round 6 repros ───────────────────────


def _add_imported(db, user_id, name, value, **kw):
    """与 pdf_parser / family_health 导入同形: item_code 由 normalize_item_name(name) 派生。"""
    from app.services.exam_packages import normalize_item_name

    code, _label = normalize_item_name(name)
    return _add(db, user_id, name, value, item_code=code or None, **kw)


class TestRound6DerivedCodeCannotOverrideDisplayName:
    def test_urine_ph_imported_never_uric_acid(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add_imported(db, user.id, "UA-PH", 8.0)
        db.commit()
        assert "uric_acid" not in fetch_latest_labs(db, user.id)

    def test_urine_sg_does_not_hide_serum_uric_acid(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add_imported(db, user.id, "尿酸", 480.0, day=OLD_DAY)
        _add_imported(db, user.id, "UA-SG", 1.025)
        _add_imported(db, user.id, "UA-PRO", 0.3)
        db.commit()
        assert fetch_latest_labs(db, user.id)["uric_acid"] == 480.0

    def test_urine_creatinine_imported_not_serum(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add_imported(db, user.id, "肌酐", 80.0, day=OLD_DAY)
        _add_imported(db, user.id, "UCr", 9000.0)
        db.commit()
        assert fetch_latest_labs(db, user.id)["creatinine"] == 80.0

    def test_bare_registry_code_alone_does_not_admit_ambiguous_name(self, db):
        # 「血清」+ item_code UA: 裸 registry code 是旧版归一化从名字派生的, 不是独立证据 → 不补认
        # (与 #259 前 main 一致, 不读 hint); 自由文本 OCR 提示见 TestReconcileLegacyCodeHintsAddNothing。
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "血清", 450.0, item_code="UA")
        db.commit()
        assert "uric_acid" not in fetch_latest_labs(db, user.id)

    def test_imported_real_serum_uric_acid(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add_imported(db, user.id, "Urate", 520.0)
        db.commit()
        assert fetch_latest_labs(db, user.id)["uric_acid"] == 520.0


class TestRound6NonBlocking:
    def test_ggt_chinese_standard_name(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add_imported(db, user.id, "γ-谷氨酰基转移酶", 120.0)
        db.commit()
        assert fetch_latest_labs(db, user.id)["ggt"] == 120.0

    @pytest.mark.parametrize("name", ["sd-LDL", "sdLDL-C"])
    def test_small_dense_ldl_not_ldl_c(self, db, name):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "LDL-C", 4.2, unit="mmol/L", day=OLD_DAY)
        _add(db, user.id, name, 1.1, unit="mmol/L")
        db.commit()
        assert fetch_latest_labs(db, user.id)["ldl"] == 4.2


# ─────────────────────── reconcile review (on #259 canonical layer) ───────────────────────


class TestReconcileSingleLiverEnzymeNeverVanishes:
    """肝酶规则要 ≥2 项才触发: 单项升高不能被算「已覆盖」而零痕迹, 必须进兜底。"""

    @pytest.mark.parametrize("name", ["丙氨酸氨基转移酶", "GPT", "天门冬氨酸转氨酶", "γ-谷氨酰基转移酶", "ALT", "AST", "GGT"])
    def test_single_enzyme_surfaces(self, name):
        a = _alerts(_twin([_item(name, 300.0, "U/L")]))
        assert "labs.liver_enzyme_pattern" not in a
        assert name in _uncategorized(a)

    def test_ratio_plus_single_enzyme_both_surface(self):
        a = _alerts(_twin([_item("AST/ALT", 2.5), _item("ALT", 80.0, "U/L")]))
        assert {"AST/ALT", "ALT"} <= set(_uncategorized(a))

    def test_enzymes_used_by_firing_rule_are_covered(self):
        a = _alerts(_twin([_item("ALT", 250.0, "U/L"), _item("AST", 210.0, "U/L")]))
        assert a["labs.liver_enzyme_pattern"].severity == Severity.CRITICAL
        assert "ALT" not in _uncategorized(a) and "AST" not in _uncategorized(a)


class TestReconcileLegacyCodeHintsAddNothing:
    """存量行 name_en = item_code = 旧版 normalize_item_name(名字) 派生的 registry code: 不是独立信息,
    不能把显示名认不出的别的项目 (UACR / Gastrin / Crystals) 补认成该指标。"""

    @pytest.mark.parametrize("key,real_name,real,decoy,code,decoy_val", [
        ("uric_acid", "尿酸", 480.0, "UACR", "UA", 18.0),
        ("uric_acid", "尿酸", 480.0, "尿微量白蛋白(UALB)", "UA", 18.0),
        ("ast", "谷草转氨酶", 30.0, "GASTRIN", "AST", 100.0),
        ("ast", "谷草转氨酶", 30.0, "管型(CAST)", "AST", 3.0),
        ("creatinine", "肌酐", 150.0, "Crystals", "CREA", 3.0),
    ])
    def test_registry_code_hint_does_not_admit_other_item(self, db, key, real_name, real, decoy, code, decoy_val):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, real_name, real, day=OLD_DAY)
        _add(db, user.id, decoy, decoy_val, name_en=code, item_code=code)
        db.commit()
        assert fetch_latest_labs(db, user.id)[key] == real

    def test_free_text_ocr_hint_still_admits(self, db):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, "Serum lipid panel item 3", 4.9, unit="mmol/L", name_en="LDL-C", item_code="LDL-C")
        db.commit()
        assert fetch_latest_labs(db, user.id)["ldl"] == 4.9


class TestReconcilePrefilterIsNotIdentity:
    """SQL 宽前缀只负责捞行, 不能当身份关键字。"""

    @pytest.mark.parametrize("key,real_name,real,decoy,decoy_val,unit", [
        ("egfr", "eGFR", 95.0, "Anti-Glomerular Basement Membrane Ab", 2.5, "RU/mL"),
        ("alt", "谷丙转氨酶", 30.0, "丙氨酸", 350.0, "μmol/L"),
        ("ast", "谷草转氨酶", 30.0, "天冬氨酸", 40.0, "μmol/L"),
        ("ldl", "LDL-C", 4.6, "Low density lipoprotein receptor", 1.0, None),
    ])
    def test_prefilter_word_does_not_admit(self, db, key, real_name, real, decoy, decoy_val, unit):
        from app.twin._collectors import fetch_latest_labs

        user = _user(db)
        _add(db, user.id, real_name, real, day=OLD_DAY)
        _add(db, user.id, decoy, decoy_val, unit=unit)
        db.commit()
        assert fetch_latest_labs(db, user.id)[key] == real

    def test_anti_gbm_never_kidney_alert(self):
        assert "labs.egfr_decline" not in _alerts(_twin([_item("Anti-Glomerular Basement Membrane Ab", 2.5, "RU/mL")]))

    @pytest.mark.parametrize("name", ["Urate crystals", "Uric acid crystals"])
    def test_urate_crystals_not_uric_acid(self, name):
        a = _alerts(_twin([_item(name, 12.0)]))
        assert "labs.uric_acid_high" not in a
        assert name in _uncategorized(a)

    @pytest.mark.parametrize("name", ["UA (uricase)", "Serum UA (Uricase)", "UA enzymatic"])
    def test_method_words_keep_serum_ua(self, name):
        assert _alerts(_twin([_item(name, 560.0)]))["labs.uric_acid_high"].severity == Severity.MEDIUM
