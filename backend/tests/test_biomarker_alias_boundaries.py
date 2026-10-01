"""别名边界感知匹配 + 单位三态 (2026-09-30 事故: VLDL-C 存成 LDL, eGFR/尿肌酐存成肌酐).

子串匹配把「低密度脂蛋白」命中「极低密度脂蛋白」、「LDL」命中「VLDL」、「肌酐」命中「尿肌酐」、
ASCII 短别名 Cr/TG/TC/Hb 命中 EPI-cr/CRP、TgAb、QTc、HBsAg。每条都钉住期望 code
(None = 不得进入任何 registry 序列)。数值均为合成值。
"""
import pytest

from app.biomarkers import normalize_observation, resolve_code
from app.biomarkers.definitions import REGISTRY
from app.biomarkers.normalize import reading_for_code
from app.services.exam_packages import normalize_item_name


EXPECTED_CODES = {
    # ── 血脂: VLDL / sdLDL / 非 HDL 不是 LDL/HDL/TC ──
    "极低密度脂蛋白-C": None,
    "极低密度脂蛋白胆固醇": None,
    "VLDL-C": None,
    "sdLDL-C": None,
    "sd LDL-C": None,
    "小而密低密度脂蛋白": None,
    "非高密度脂蛋白胆固醇": None,
    "non-HDL-C": None,
    "LDL-C/HDL-C": None,
    "低密度脂蛋白-C": "lipid_ldl",
    "低密度脂蛋白": "lipid_ldl",
    "LDL-C": "lipid_ldl",
    "低密度脂蛋白胆固醇(LDL-C)": "lipid_ldl",
    "低密度脂蛋白胆固醇（LDL-C）": "lipid_ldl",
    "LDL-C(直接法)": "lipid_ldl",
    "LDL Cholesterol": "lipid_ldl",
    "LDL-C mmol/L": "lipid_ldl",       # 名字里夹带单位, 单位里的「/」不是比值
    "高密度脂蛋白-C": "lipid_hdl",
    "总胆固醇": "lipid_tc",
    "胆固醇": "lipid_tc",
    "TCH": "lipid_tc",
    "QTc": None,
    "甘油三酯": "lipid_tg",
    "甘油三脂": "lipid_tg",
    "TG": "lipid_tg",
    "TgAb": None,
    "甲状腺球蛋白抗体(TgAb)": None,
    "甲状腺球蛋白(Tg)": None,
    # ── 肌酐: eGFR / 尿肌酐 / 清除率 / CRP / ACR / 比值 都不是血肌酐 ──
    "肌酐": "CREA",
    "血肌酐": "CREA",
    "Cr": "CREA",
    "CRE": "CREA",
    "CREAT": "CREA",
    "肌酐(酶法)": "CREA",
    "肌酐(比色法)": "CREA",           # 「比色法」不是比值
    "Creatinine": "CREA",
    "肌酐/CREA": "CREA",
    "肾小球滤过率(EPI-cr)": "egfr",
    "肾小球滤过率(EPI-cys)": "egfr",
    "EPI-cr": None,
    "尿肌酐": None,
    "尿液肌酐": None,
    "24小时尿肌酐": None,
    "肌酐清除率": None,
    "Ccr": None,
    "UACR": None,
    "hs-CRP": None,
    "超敏C反应蛋白(hs-CRP)": None,
    "Creatine kinase": None,
    "尿素氮/肌酐": None,
    "尿素氮/肌酐比值": None,
    "尿素氮肌酐比(BUN/Cr)": None,
    "尿素肌酐比(UREA/CREA)": None,
    "尿素氮与肌酐比": None,
    "尿素氮": "BUN",
    # ── eGFR 家族 ──
    "eGFRcr": "egfr",
    "eGFRcys": "egfr",
    "eGFRcr-cys": "egfr",
    "eGFR2021": "egfr",
    "EGFR基因突变": None,
    # ── 尿酸 / 血红蛋白 / 糖 ──
    "尿酸": "UA",
    "UricAcid": "UA",
    "SUA": "UA",
    "尿酸结晶": None,
    "尿酸碱度": None,
    "血红蛋白": "hemoglobin",
    "HGB": "hemoglobin",
    "Hemoglobin concentration": "hemoglobin",   # concentration 含 ratio 子串, 不是比值
    "平均红细胞血红蛋白浓度": None,
    "平均红细胞血红蛋白量": None,
    "HBsAg": None,
    "糖化血红蛋白": "glucose_hba1c",
    "Hemoglobin A1c": "glucose_hba1c",
    "糖化白蛋白": None,
    "空腹血糖": "glucose_fasting",
    "FPG": "glucose_fasting",
    "尿葡萄糖": None,
    "餐后2小时血糖": None,
    "GLU-1h": None,                 # 负荷后/定时/尿/脑脊液 的葡萄糖都不是空腹血糖
    "1小时血糖": None,
    "葡萄糖(60min)": None,
    "GLU 30min": None,
    "GLU-3h": None,
    "GLU-PC": None,
    "服糖后1小时血糖": None,
    "GLU(尿)": None,
    "葡萄糖(尿)": None,
    "U-GLU": None,
    "Glucose (CSF)": None,
    "GLU-F": "glucose_fasting",
    "空腹血糖(服糖前)": "glucose_fasting",   # 负荷前 = 空腹
    "空腹血糖(负荷前)": "glucose_fasting",
    "空腹血糖(禁食8-12h)": "glucose_fasting",  # 12h 是禁食时长, 不是 2h 时间点
    "尿 肌酐": None,
    "Plasma Creatinine": "CREA",        # 去空格只能用于中文排除词 (plasmacreatinine 含 acr)
    "Enzymatic Creatinine": "CREA",
    "Enzymatic Cr": "CREA",
    "Plasma Cr": "CREA",
    "OGTT空腹血糖": "glucose_fasting",
    "空腹血糖(OGTT)": "glucose_fasting",
    "OGTT 2h血糖": None,
    "肌酐 尿": None,
    "尿 尿酸": None,
    "肌酐(尿)": None,
    "尿酸(尿)": None,
    "TG-Ab": None,
    "Anti-Tg": None,
    "Cr-Cl": None,
    "A/G ratio": None,
    # ── 肝酶 ──
    "ALT/AST": None,
    "ALT/GPT": "ALT",
    "SGPT": "ALT",
    "AST/GOT": "AST",
    "谷氨酰转肽酶": "GGT",
    "γ-谷氨酰转移酶": "GGT",
    # ── 2026-10-01 analyte-guard 并入 (见 test_safety_lab_analyte_guard.py 各轮评审复现) ──
    "EGFR exon 19 deletion": None,
    "EGFR 19del": None,
    "EGFRvIII": None,
    "EGFR拷贝数": None,
    "EGFR蛋白表达": None,
    "EGFR IHC": None,
    "eGFR (表达式计算)": "egfr",
    "eGFRcreat": "egfr",
    "eGFREPI": "egfr",
    "CKD-EPI": "egfr",
    "eGFR (Estimated Glomerular Filtration Rate)": "egfr",
    "Glomerular Filtration Rate": "egfr",
    "Low Density Lipoprotein Cholesterol": "lipid_ldl",
    "High Density Lipoprotein Cholesterol": "lipid_hdl",
    "LDLcalc": "lipid_ldl",
    "LDLD": "lipid_ldl",
    "LDL-TG": None,
    "低密度脂蛋白甘油三酯": None,
    "LDL-C(TG<4.5)": "lipid_ldl",
    "LDLR": None,
    "UA-PH": None,
    "UA, pH": None,
    "UA-SG": None,
    "UA-PRO": None,
    "UA Glucose": None,
    "血清UA": "UA",
    "S-UA": "UA",
    "UA(酶法)": "UA",
    "Serum UA": "UA",
    "Urate": "UA",
    "GOT2": None,
    "GPT2": None,
    "天门冬氨酸转氨酶": "AST",
    "γ-谷氨酰基转移酶": "GGT",
    "铬(Cr)": None,
    "Glycated albumin": None,
    "HbA1c (NGSP/IFCC)": "glucose_hba1c",
}


@pytest.mark.parametrize("name,expected", EXPECTED_CODES.items())
def test_resolve_code_is_boundary_aware(name, expected):
    assert resolve_code(name) == expected


@pytest.mark.parametrize("name,expected", EXPECTED_CODES.items())
def test_exam_normalizer_never_assigns_a_different_registry_code(name, expected):
    """写入期 (PDF 解析 / create_indicator_from_item / 图片报告) 的归一化器不能给出别的 registry code。

    它的映射表不收录血脂等中文名 (未识别 → ""), 也可以给出 registry 外的 code (如 thyroid_tgab);
    但只要给出 REGISTRY 里的 code, 就必须与 resolve_code 一致 —— 否则 PDF 解析会把项目名改成错的标签。
    """
    code = normalize_item_name(name)[0]
    if expected is not None:
        assert code in (expected, ""), f"{name!r} → {code!r}"
    else:
        assert code not in REGISTRY, f"{name!r} → {code!r}"


@pytest.mark.parametrize("name,wrong_code", [
    ("球蛋白", "thyroid_tgab"),        # 反向包含: 「球蛋白」⊂「甲状腺球蛋白抗体」
    ("淋巴细胞", "immune_bcell"),       # 反向包含: 「淋巴细胞」⊂「B淋巴细胞」
])
def test_exam_normalizer_drops_reverse_containment(name, wrong_code):
    assert normalize_item_name(name)[0] != wrong_code


@pytest.mark.parametrize("name,code", [
    ("尿素", "BUN"),                      # 旧逻辑靠反向包含 (尿素 ⊂ 尿素氮) 命中; 删反向后须显式收录
    ("25-羟基维生素D（总）", "bone_vitd"),
    ("SCr", "CREA"),                      # 映射表没收录的写法由 resolve_code 兜底 (只认历来产出的 code)
    ("CRE", "CREA"),
    ("GPT", "ALT"),
])
def test_exam_normalizer_keeps_legitimate_mappings(name, code):
    assert normalize_item_name(name)[0] == code


def test_exam_normalizer_introduces_no_new_codes():
    """兜底只认历来会产出的 code: eGFR / 血脂写法不能突然带上 item_code (单项校正按 exam+item_code 关联)。"""
    assert normalize_item_name("eGFRcr")[0] == ""
    assert normalize_item_name("低密度脂蛋白-C")[0] == ""


@pytest.mark.parametrize("name", ["25-羟基维生素D2", "25-羟基维生素D3"])
def test_exam_normalizer_does_not_relabel_vitamin_d_fraction_as_total(name):
    """旧逻辑把 D2/D3 分量归 bone_vitd, PDF 解析随即把项目名改成总量标签「25羟维生素D」。"""
    assert normalize_item_name(name) == ("", name)


def test_exclusions_never_block_own_aliases():
    """配置自检: 某定义的排除词若出现在它自己的别名里, 该别名将永远解析不到 (静默失效)。"""
    from app.biomarkers.definitions import _norm_text

    for defn in REGISTRY.values():
        for alias in (defn.code, defn.display, *defn.aliases):
            norm = _norm_text(alias)
            hits = [ex for ex in defn.excludes if _norm_text(ex) in norm]
            assert not hits, f"{defn.code}: alias {alias!r} contains own exclusion {hits}"
            assert resolve_code(alias) == defn.code, f"{defn.code}: alias {alias!r} no longer resolves"


# ── 单位三态: 可换算 / 已识别但量纲不符 (拒收) / 未识别 (按 canonical 读, 不确定≠不是) ──

@pytest.mark.parametrize("name,value,unit", [
    ("肌酐", 96, "ml/min"),                  # eGFR 的值被当肌酐
    ("肌酐", 2.4, "mg/g"),                   # 尿肌酐/ACR 被当血肌酐
    ("血红蛋白", 29.8, "pg"),                # MCH 被写入期归一化器改名为「血红蛋白」
    ("甘油三酯", 17.0, "IU/mL"),             # 抗体滴度单位
    ("尿酸", 21.7, "ng/mL"),                 # OCR 把别的项目标成尿酸
])
def test_recognised_incompatible_unit_is_rejected(name, value, unit):
    assert normalize_observation(name, value, unit) is None


@pytest.mark.parametrize("name,value,unit,expected", [
    ("低密度脂蛋白胆固醇", 5.3, "-", 5.3),       # 占位符 = 缺单位
    ("LDL-C", 5.3, "mmoI/L", 5.3),             # OCR 变体: 未识别, 不是异量纲证据
    ("低密度脂蛋白胆固醇", 5.3, "毫摩尔/升", 5.3),
    ("糖化血红蛋白", 6.3, "%(NGSP)", 6.3),     # 注释括号
    ("谷丙转氨酶", 118, "U/L(37℃)", 118),
    ("ALT", 30, "weird-unit", 30),
])
def test_unrecognised_unit_spelling_reads_as_canonical(name, value, unit, expected):
    o = normalize_observation(name, value, unit)
    assert o is not None and o.normalized_value == expected


def test_unrecognised_unit_is_marked_low_confidence():
    assert normalize_observation("LDL-C", 5.3, "mmoI/L").confidence == "low"
    assert normalize_observation("LDL-C", 5.3, "-").confidence == "high"  # 占位符 = 缺单位, 沿用旧约定


@pytest.mark.parametrize("name,value,unit,expected", [
    ("糖化血红蛋白", 53, "mmol/mol(IFCC)", 7.0),
    ("尿酸", 0.455, "mmol/L", 455.0),
    ("肌酐", 0.083, "mmol/L", 83.0),
    ("eGFR", 0.45, "ml/s/1.73m2", 27.0),
    ("谷丙转氨酶", 2.0, "μkat/L", 120.0),
    ("血红蛋白", 14.6, "g/dL", 146.0),
    ("血红蛋白", 14.6, None, 146.0),             # 缺单位的小数值是 g/dL 写法
    ("糖化血红蛋白", 53, None, 7.0),             # 缺单位的 20–200 是 IFCC mmol/mol
    ("肌酐", 1.6, None, 141.44),                 # 缺单位的小数值是 mg/dL
    ("低密度脂蛋白-C", 1.2, "g/L", 3.103),
])
def test_unit_conversions(name, value, unit, expected):
    o = normalize_observation(name, value, unit)
    assert o is not None
    assert o.normalized_value == pytest.approx(expected, abs=0.01)


def test_implausible_values_are_rejected():
    """MCHC (~330 g/L) 被改名成「血红蛋白」—— 单位同为 g/L, 只能靠合理区间挡; 尿肌酐量级同理。"""
    assert normalize_observation("血红蛋白", 338, "g/L") is None
    assert normalize_observation("肌酐", 9.1, "mmol/L") is None     # 9100 μmol/L: 尿肌酐量级
    ok = normalize_observation("血红蛋白", 146, "g/L", sex="male")
    assert ok is not None and ok.code == "hemoglobin" and ok.flag == "normal"


@pytest.mark.parametrize("unit", ["ml/min", "mL/min/1.73m²", "ml/min/1.73m2", "mL/min/{1.73_m2}",
                                  "ml/(min·1.73m²)", "ml/分/1.73m2"])
def test_egfr_unit_spellings_are_canonical(unit):
    o = normalize_observation("肾小球滤过率(EPI-cr)", 96, unit)
    assert o is not None
    assert o.code == "egfr"
    assert o.confidence == "high"
    assert o.flag == "normal"


@pytest.mark.parametrize("unit", ["μmol/L", "µmol/L", "umol/L", "μmol/l", "微摩尔/升"])
def test_micromolar_spellings_are_canonical(unit):
    """希腊字母 μ (U+03BC) 与微符号 µ (U+00B5) 混用; 必须等价, 否则全部被判 low。"""
    o = normalize_observation("肌酐", 83, unit, sex="male")
    assert o is not None
    assert o.code == "CREA"
    assert o.confidence == "high"
    assert o.normalized_value == 83


def test_missing_unit_still_assumes_canonical():
    o = normalize_observation("谷丙转氨酶", 26, None, sex="male")
    assert o is not None and o.code == "ALT" and o.confidence == "high"
    assert normalize_observation("谷丙转氨酶", 26, "IU/L").confidence == "high"


# ── Safety/Twin 读数: 别名表没收录的写法按旧关键字兜底, 只有「肯定是别的项目」才排除 ──

@pytest.mark.parametrize("name,unit,code,keywords,expected", [
    ("Uric", "μmol/L", "UA", ("uric",), 5.3),                           # 名字不认识但含旧关键字
    ("极低密度脂蛋白-C", "mmol/L", "lipid_ldl", ("低密度脂蛋白",), None),  # 含关键字但肯定不是
    ("hs-CRP", "mg/L", "CREA", ("Cr",), None),
    ("肌酐", "mg/g", "CREA", ("肌酐",), None),                          # 单位已识别且不符
    ("eGFR", "-", "egfr", ("eGFR",), 5.3),                               # 占位符单位照读
    # 旧关键字兜底同样要有 ASCII 词边界, 否则缺单位时把别的项目读成该指标
    ("QTc", None, "lipid_tc", ("TC",), None),
    ("TgAb", None, "lipid_tg", ("TG",), None),
    ("UACR", None, "UA", ("UA",), None),
    ("CrCl", None, "CREA", ("Cr",), None),
])
def test_reading_for_code(name, unit, code, keywords, expected):
    assert reading_for_code(name, 5.3, unit, code, keywords) == expected
