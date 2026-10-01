"""Biomarker 定义注册表 — 代谢健康 MVP 面板 (PRD P1, G3).

把 exam_packages.py 的"别名→canonical code"映射, 升级为带:
  - 标准单位 (canonical_unit)
  - 单位换算 (mg/dL ↔ mmol/L, mmol/mol → %, ...)
  - 按性别的参考范围 (ref_ranges)
  - 风险域 (domain) 与风险方向 (higher_is_risk)

的完整定义。这是 BiomarkerObservation 归一化的真相源。

为什么用 Python 注册表而非 DB 表:
  - 这是"定义/知识", 不是用户数据; 适合代码评审 + 单测, 无需种子迁移。
  - 与 Safety Guardian labs.py 的硬编码阈值可逐步收口到这里 (后续)。

canonical code 对齐 exam_packages.py 既有命名 (lipid_ldl / glucose_fasting / ALT / CREA / UA ...)。
注意: exam_packages 的别名表缺核心血脂 (低密度脂蛋白等) 的中文别名 —— 这里补齐。

参考范围为成人通用默认值; 实验室专属范围 (按 lab/年龄细化) 是后续工作。

名字与单位的判定是安全敏感的 (code 喂给 Safety Guardian / Twin / 干预周期):
  - 名字 (resolve_code): 边界感知别名 + 每个定义的排除词 + 比值拒识。2026-09-30 事故: 纯子串匹配把
    「极低密度脂蛋白-C」存成 LDL、「肾小球滤过率(EPI-cr)」「尿肌酐」存成肌酐。
  - 单位 (unit_status): 可换算 / 已识别但量纲不符 (肌酐 ml/min、血红蛋白 pg —— 肯定是别的项目) /
    未识别 (OCR 变体、注释、占位符)。未识别只是不确定, 按旧约定当 canonical 读, 绝不当成「不是该指标」。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class RefRange:
    low: Optional[float] = None
    high: Optional[float] = None
    sex: Optional[str] = None        # "male" / "female" / None(通用)
    age_lo: Optional[int] = None     # 含
    age_hi: Optional[int] = None     # 含

    def matches(self, sex: Optional[str], age: Optional[int]) -> bool:
        if self.sex is not None and sex is not None and self.sex != sex:
            return False
        if self.age_lo is not None and age is not None and age < self.age_lo:
            return False
        if self.age_hi is not None and age is not None and age > self.age_hi:
            return False
        return True


@dataclass(frozen=True)
class BiomarkerDefinition:
    code: str
    display: str
    domain: str                              # lipid/glucose/liver/kidney/metabolic
    canonical_unit: str
    aliases: tuple[str, ...] = ()
    ref_ranges: tuple[RefRange, ...] = ()
    # 其它单位(经 _norm_unit) -> 乘以该系数得到 canonical_unit 值
    unit_conversions: dict = field(default_factory=dict)
    # True: 偏高为风险(LDL/TG/尿酸/肝酶...); False: 偏低为风险(HDL/eGFR)
    higher_is_risk: bool = True
    # 项目名含任一排除词 → 不是本指标 (即使别名命中): LDL 排除「极低密度」, 肌酐排除「尿肌酐」「肾小球」…
    excludes: tuple[str, ...] = ()
    # canonical 单位下的合理区间; 超出 → 视为串项 (MCHC≈330 g/L 被写入期改名成「血红蛋白」)
    plausible: Optional[tuple[float, float]] = None
    # (阈值, 乘数): 缺单位/未识别单位且数值低于阈值时按小单位换算 (血红蛋白 14.5 是 g/dL 写法 → 145 g/L)
    small_unit: Optional[tuple[float, float]] = None
    # 缺单位/未识别单位时, 名字必须含其一才采信 (裸「中性粒细胞」计数与百分比共用, 0.58 可能是比例)
    count_qualifiers: tuple[str, ...] = ()
    # 缺单位/未识别单位时数值上限 (缺单位的 PT 98 是活动度 %, 不是 98 秒)
    unitless_max: Optional[float] = None

    def resolve_range(self, sex: Optional[str], age: Optional[int]) -> Optional[RefRange]:
        # 先找最具体(性别匹配)的, 再退化到通用.
        specific = [r for r in self.ref_ranges if r.sex == sex and r.matches(sex, age)]
        if specific:
            return specific[0]
        generic = [r for r in self.ref_ranges if r.matches(sex, age)]
        return generic[0] if generic else None


# ── 单位 ───────────────────────────────────────────────────
# 占位符 = 没有单位信息 (比值项常写「-」)
_UNIT_PLACEHOLDERS = frozenset({"-", "--", "—", "–", "/", "无", "none", "null", "n/a", "na"})
_UNIT_SYNONYMS = {
    "umol/l": "μmol/l", "毫摩尔/升": "mmol/l", "微摩尔/升": "μmol/l", "克/升": "g/l",
    "毫克/分升": "mg/dl", "单位/升": "u/l", "ukat/l": "μkat/l", "秒": "s", "sec": "s",
}
_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
# 已识别的化验单位 (任何量纲)。已识别却换算不到某指标 canonical 的单位 = 肯定不是该指标;
# 不在表里的写法 (mmoI/L 这类 OCR 变体) 只是未识别。
_KNOWN_UNITS = frozenset({
    "mol/l", "mmol/l", "μmol/l", "nmol/l", "pmol/l",
    "g/l", "g/dl", "mg/dl", "mg/l", "μg/l", "ug/l", "μg/dl", "ug/dl", "mg/ml", "μg/ml", "ug/ml",
    "ng/ml", "ng/dl", "ng/l", "pg/ml",
    "u/l", "iu/l", "μkat/l", "u/ml", "iu/ml", "miu/ml", "miu/l", "μiu/ml", "uiu/ml",
    "%", "mg/g", "mg/mmol", "mmol/mol",
    "10^9/l", "10e9/l", "10^12/l", "10e12/l", "/μl", "/ul", "个/μl", "/hp", "pg", "fl",
    "s", "秒", "mmhg", "s/co", "coi",
})
_FLOW_PREFIXES = ("ml/min", "ml/分", "ml/s")


def _norm_unit(u: Optional[str]) -> str:
    """单位归一: NFKC(µ→μ、²→2、㎡→m2) + 小写 + 去空白; 去注释括号 (%(NGSP)、mmol/mol(IFCC)、U/L(37℃));
    占位符 → ""; 中文写法 → 标准写法; 计数单位 ×10⁹/L、x10^9/L、10*9/L → 10^9/L。"""
    # 上标指数先改成 ^n (NFKC 会把 10⁹ 压成 109); 只动 10 后面的, m² 仍归一成 m2
    s = re.sub(r"10([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda m: "10^" + m.group(1).translate(_SUPERSCRIPT_DIGITS), u or "")
    s = unicodedata.normalize("NFKC", s).strip().lower()
    s = re.sub(r"\s+", "", s).replace("·", "/")
    s = re.sub(r"^[×x*](?=10)", "", s)
    s = re.sub(r"^10\*(\d+)", r"10^\1", s)
    if s.startswith("ml/("):  # ml/(min·1.73m²): 括号是结构, 不是注释
        s = s.replace("(", "").replace(")", "")
    else:
        s = re.sub(r"\([^)]*\)", "", s)
    if s in _UNIT_PLACEHOLDERS:
        return ""
    return _UNIT_SYNONYMS.get(s, s)


# ── 代谢健康 MVP 面板 ─────────────────────────────────────
_DEFS: tuple[BiomarkerDefinition, ...] = (
    # 血脂
    BiomarkerDefinition(
        code="lipid_ldl", display="低密度脂蛋白胆固醇", domain="lipid", canonical_unit="mmol/L",
        aliases=("低密度脂蛋白", "低密度脂蛋白胆固醇", "LDL", "LDL-C", "LDL-胆固醇", "LDLC"),
        ref_ranges=(RefRange(high=3.4),),
        unit_conversions={"mg/dl": 1 / 38.67, "g/l": 2.586},
        higher_is_risk=True,
        excludes=("极低密度", "vldl", "小而密", "sdldl", "sd-ldl", "sd ldl", "氧化", "oxldl", "ox-ldl",
                  "颗粒", "ldl-p"),
    ),
    BiomarkerDefinition(
        code="lipid_hdl", display="高密度脂蛋白胆固醇", domain="lipid", canonical_unit="mmol/L",
        aliases=("高密度脂蛋白", "高密度脂蛋白胆固醇", "HDL", "HDL-C", "HDLC"),
        ref_ranges=(RefRange(low=1.0, sex="male"), RefRange(low=1.3, sex="female"), RefRange(low=1.0)),
        unit_conversions={"mg/dl": 1 / 38.67, "g/l": 2.586},
        higher_is_risk=False,  # 偏低为风险
        excludes=("非高密度", "非hdl", "non-hdl", "non hdl", "nonhdl", "颗粒", "hdl-p"),
    ),
    BiomarkerDefinition(
        code="lipid_tg", display="甘油三酯", domain="lipid", canonical_unit="mmol/L",
        aliases=("甘油三酯", "甘油三脂", "三酰甘油", "TG", "TRIG", "TRIGL", "triglyceride", "triglycerides"),
        ref_ranges=(RefRange(high=1.7),),
        unit_conversions={"mg/dl": 1 / 88.57, "g/l": 1.129},
        higher_is_risk=True,
        excludes=("甲状腺", "球蛋白", "tg-ab", "anti-tg", "抗tg"),  # 甲状腺球蛋白(Tg) / 抗体(TgAb)
    ),
    BiomarkerDefinition(
        code="lipid_tc", display="总胆固醇", domain="lipid", canonical_unit="mmol/L",
        aliases=("总胆固醇", "胆固醇", "TC", "CHOL", "TCHO", "TCH", "T-CHO", "T-CHOL", "cholesterol",
                 "total cholesterol"),
        ref_ranges=(RefRange(high=5.2),),
        unit_conversions={"mg/dl": 1 / 38.67, "g/l": 2.586},
        higher_is_risk=True,
        # 「胆固醇」是 HDL-C / LDL-C / VLDL-C / 非 HDL-C 的子串: 这些都不是总胆固醇
        excludes=("高密度", "低密度", "hdl", "ldl", "游离", "胆固醇酯", "残余", "残粒"),
    ),
    # 血糖
    BiomarkerDefinition(
        code="glucose_fasting", display="空腹血糖", domain="glucose", canonical_unit="mmol/L",
        aliases=("空腹血糖", "葡萄糖", "血糖", "GLU", "GLUC", "FBG", "FPG", "GLU-F", "glucose", "fasting glucose"),
        ref_ranges=(RefRange(low=3.9, high=6.1),),
        unit_conversions={"mg/dl": 1 / 18.0, "g/l": 5.551},
        higher_is_risk=True,
        # 尿糖/餐后/负荷后/随机 不是空腹血糖 (排除词要能放进自由文本: 「糖尿病」不含「尿糖」)
        # 负荷后时间点 (1h/60min/2小时…) 另由 _GLUCOSE_TIMEPOINT_RE 按完整数字匹配 (「禁食8-12h」不算)
        excludes=("尿糖", "尿葡萄糖", "(尿)", "尿glu", "u-glu", "ua-glu", "尿液", "urine", "csf", "脑脊液", "胸水",
                  "腹水", "餐后", "postprandial", "-pc", " pc", "服糖后", "负荷后", "半小时", "两小时", "随机",
                  "random", "ogtt", "糖耐", "tolerance", "脱氢酶", "dehydrogenase", "磷酸", "phosphate"),
    ),
    BiomarkerDefinition(
        # 标准糖化(NGSP A1c). bare「糖化血红蛋白」按惯例就是这个标准指标。
        code="glucose_hba1c", display="糖化血红蛋白", domain="glucose", canonical_unit="%",
        aliases=("糖化血红蛋白", "糖化血红蛋白测定", "糖化血红蛋白A1c", "糖化", "HbA1c", "HbA1C", "GHb", "A1C",
                 "hemoglobin a1c", "glycated hemoglobin"),
        ref_ranges=(RefRange(high=5.7),),
        # IFCC mmol/mol → NGSP%: %≈mmol/mol/10.929+2.15; 在 to_canonical_unit 里特判
        unit_conversions={},
        higher_is_risk=True,
        excludes=("白蛋白", "血清蛋白", "果糖胺"),  # 糖化白蛋白 / 糖化血清蛋白 不是 A1c
        plausible=(0.0, 20.0),  # 血红蛋白 g/L(~160) 被名字滑进糖化序列时挡掉 (缺单位的 20–130 按 IFCC 换算)
    ),
    BiomarkerDefinition(
        # 总糖化血红蛋白(HbA1, 参考 6.3–9.0%), 与标准 A1c 是不同指标 —— 别名误判过它(锚点用户 user 3)。
        code="glucose_hba1_total", display="糖化血红蛋白A1", domain="glucose", canonical_unit="%",
        aliases=("糖化血红蛋白A1", "HbA1", "GHbA1"),
        ref_ranges=(RefRange(low=6.3, high=9.0),),
        unit_conversions={},
        higher_is_risk=True,
        plausible=(0.0, 20.0),
    ),
    # 血液学
    BiomarkerDefinition(
        # 血红蛋白(g/L). 历史误判进糖化序列(「血红蛋白」是「糖化血红蛋白」的子串)。
        code="hemoglobin", display="血红蛋白", domain="hematology", canonical_unit="g/L",
        aliases=("血红蛋白", "血色素", "Hb", "HGB", "HGB-总", "HB"),
        ref_ranges=(RefRange(low=130, high=175, sex="male"), RefRange(low=115, high=150, sex="female"),
                    RefRange(low=115, high=175)),
        unit_conversions={"g/dl": 10.0},
        higher_is_risk=False,  # 高低均可异常; 保守取 False(偏低=贫血风险)
        # MCH/MCHC(平均…血红蛋白…)、网织/游离/尿血红蛋白、HbA2、糖化 都不是全血血红蛋白
        excludes=("糖化", "a1c", "glyc", "平均", "网织", "还原", "氧合", "碳氧", "高铁", "胎儿", "电泳",
                  "尿血红蛋白", "(尿)", "尿液", "游离", "分布宽度", "a2"),
        plausible=(20.0, 250.0),  # MCHC 常见 316–354 g/L
        small_unit=(25.0, 10.0),
    ),
    BiomarkerDefinition(
        # 中性粒细胞绝对值(10^9/L)。体检里同名「中性粒细胞」也常是百分比 —— 靠单位 % (异量纲) 与
        # 合理区间 (缺单位的 55 不是绝对值) 挡掉。参考范围 WS/T 405 成人 1.8–6.3。
        code="NEUT", display="中性粒细胞绝对值", domain="hematology", canonical_unit="10^9/L",
        aliases=("中性粒细胞", "中性粒细胞绝对值", "中性粒细胞计数", "中性粒细胞数", "中性粒细胞总数",
                 "NEUT", "NEUT#", "NEU#", "NE#", "ANC", "neutrophil count", "absolute neutrophil count",
                 "neutrophils"),
        ref_ranges=(RefRange(low=1.8, high=6.3),),
        # G/L = giga/L (计数不可能是克/升, 只在本定义里这样解读)
        unit_conversions={"10e9/l": 1.0, "10^3/μl": 1.0, "10^3/ul": 1.0, "k/μl": 1.0, "k/ul": 1.0, "g/l": 1.0,
                          "/μl": 0.001, "/ul": 0.001, "个/μl": 0.001},
        higher_is_risk=False,  # 高低均可异常; 偏低 (粒缺) 为风险
        # 百分比 / 嗜酸嗜碱 / ANCA / NAP / NGAL / 杆状分叶分类 / 体液 都不是外周血中性粒细胞绝对值
        excludes=("%", "百分", "比例", "比率", "率", "相对", "relative", "嗜酸", "嗜碱", "胞浆", "抗体", "anca",
                  "碱性磷酸酶", "明胶酶", "ngal", "弹性蛋白酶", "杆状", "分叶", "脑脊液", "胸水", "腹水", "积液",
                  "关节液", "穿刺", "骨髓", "痰", "尿", "吞噬", "趋化", "功能", "cd64", "-ri", "-gi"),
        plausible=(0.0, 30.0),
        count_qualifiers=("绝对值", "计数", "总数", "数", "#", "count", "absolute", "anc"),
    ),
    # 凝血
    BiomarkerDefinition(
        # 凝血酶原时间(秒)。参考范围各实验室差异大 (10.0–13.5 / 12.0–14.0), 取通用 10–14; 延长为风险。
        code="PT", display="凝血酶原时间", domain="coagulation", canonical_unit="s",
        aliases=("凝血酶原时间", "血浆凝血酶原时间", "PT", "PT时间", "prothrombin time"),
        ref_ranges=(RefRange(low=10.0, high=14.0),),
        higher_is_risk=True,
        # INR / 活动度(PTA%) / 比值 / 对照值 / 异常凝血酶原(PIVKA-II) 都不是患者 PT 秒数
        excludes=("inr", "国际标准化", "活动度", "活动", "活性", "activity", "%", "对照", "control", "正常值",
                  "参考", "异常", "pivka"),
        plausible=(5.0, 150.0),
        unitless_max=60.0,
    ),
    # 肝功能
    BiomarkerDefinition(
        code="ALT", display="谷丙转氨酶", domain="liver", canonical_unit="U/L",
        aliases=("ALT", "谷丙转氨酶", "丙氨酸氨基转移酶", "丙氨酸转氨酶", "GPT", "SGPT", "ALAT"),
        ref_ranges=(RefRange(high=50, sex="male"), RefRange(high=40, sex="female"), RefRange(high=50)),
        unit_conversions={"iu/l": 1.0, "μkat/l": 60.0},
        higher_is_risk=True,
    ),
    BiomarkerDefinition(
        code="AST", display="谷草转氨酶", domain="liver", canonical_unit="U/L",
        aliases=("AST", "谷草转氨酶", "天门冬氨酸氨基转移酶", "天冬氨酸氨基转移酶", "GOT", "SGOT", "ASAT"),
        ref_ranges=(RefRange(high=40),),
        unit_conversions={"iu/l": 1.0, "μkat/l": 60.0},
        higher_is_risk=True,
        excludes=("线粒体", "同工酶", "m-ast"),
    ),
    BiomarkerDefinition(
        code="GGT", display="谷氨酰转肽酶", domain="liver", canonical_unit="U/L",
        aliases=("GGT", "γ-谷氨酰转肽酶", "谷氨酰转肽酶", "γ-GT", "γGT", "r-GT", "GGTP", "γ-谷氨酰转移酶",
                 "谷氨酰转移酶"),
        ref_ranges=(RefRange(high=60, sex="male"), RefRange(high=45, sex="female"), RefRange(high=60)),
        unit_conversions={"iu/l": 1.0, "μkat/l": 60.0},
        higher_is_risk=True,
    ),
    # 肾功能
    BiomarkerDefinition(
        code="CREA", display="肌酐", domain="kidney", canonical_unit="µmol/L",
        aliases=("肌酐", "血肌酐", "肌酸酐", "CREA", "CREAT", "CRE", "Cr", "SCr", "creatinine"),
        ref_ranges=(RefRange(low=57, high=97, sex="male"), RefRange(low=41, high=73, sex="female"),
                    RefRange(low=44, high=106)),
        unit_conversions={"mg/dl": 88.4, "mg/l": 8.84, "mmol/l": 1000.0},
        higher_is_risk=True,
        # 尿肌酐 / 肌酐清除率 / eGFR(EPI-cr、MDRD) / 白蛋白肌酐比(ACR) / CRP / 肌酸激酶 都含「肌酐」「cr」, 都不是血肌酐
        excludes=("尿肌酐", "肌酐尿", "(尿)", "尿液", "尿cr", "尿 cr", "urine", "u-cr", "acr", "cr-cl", "清除率", "clearance",
                  "ccr", "肾小球",
                  "滤过率", "gfr", "epi", "mdrd", "cys", "胱抑素", "crp", "c反应蛋白", "c-反应蛋白", "creatine",
                  "激酶"),
        plausible=(5.0, 1500.0),  # 尿肌酐 (mmol/L 量级 ×1000) 冒充血肌酐时挡掉
        small_unit=(20.0, 88.4),  # 缺单位的小数值是 mg/dL 写法 (1.6 → 141 μmol/L)
    ),
    BiomarkerDefinition(
        code="egfr", display="估算肾小球滤过率", domain="kidney", canonical_unit="mL/min/1.73m²",
        aliases=("eGFR", "eGFRcr", "eGFRcys", "eGFRcr-cys", "eGFR2021", "eGFR2009", "eGFR-EPI", "eGFR-MDRD",
                 "估算肾小球滤过率", "肾小球滤过率", "GFR"),
        ref_ranges=(RefRange(low=90),),
        # 单位写法五花八门 (ml/min、ml/min/1.73m²、ml/分…) 都是同一量纲; mL/s 需 ×60, 见 _unit_factor
        higher_is_risk=False,  # 偏低为风险
        excludes=("基因", "突变", "mutation", "tki"),  # EGFR 基因检测不是 eGFR
    ),
    BiomarkerDefinition(
        code="UA", display="尿酸", domain="metabolic", canonical_unit="µmol/L",
        aliases=("尿酸", "血尿酸", "UA", "URIC", "UricAcid", "uric acid", "SUA"),
        ref_ranges=(RefRange(low=208, high=428, sex="male"), RefRange(low=155, high=357, sex="female"),
                    RefRange(low=155, high=428)),
        unit_conversions={"mg/dl": 59.48, "mmol/l": 1000.0},
        higher_is_risk=True,
        excludes=("结晶", "酸碱", "(尿)", "尿液", "尿尿酸", "urine", "24h", "24小时"),  # 尿酸结晶 / 尿酸碱度(pH)
        plausible=(0.0, 1500.0),
    ),
    BiomarkerDefinition(
        code="BUN", display="尿素氮", domain="kidney", canonical_unit="mmol/L",
        aliases=("尿素氮", "尿素", "BUN", "UREA"),
        ref_ranges=(RefRange(low=2.9, high=8.2),),
        unit_conversions={"mg/dl": 1 / 2.8},
        higher_is_risk=True,
        excludes=("(尿)", "尿液", "尿尿素", "urine", "24h", "24小时"),
    ),
)

# code -> def
REGISTRY: dict[str, BiomarkerDefinition] = {d.code: d for d in _DEFS}


def _norm_text(name: Optional[str]) -> str:
    """项目名归一: NFKC(全角→半角、µ→μ) + 小写 + 空白折叠。空白保留为单空格, 它是英文词边界。"""
    s = unicodedata.normalize("NFKC", name or "").strip().lower()
    return re.sub(r"\s+", " ", s)


# 别名(归一后) -> code; 同时把 code 自身、display 也并入.
_ALIAS_INDEX: dict[str, str] = {}
for _d in _DEFS:
    for _a in (_d.code, _d.display, *_d.aliases):
        _ALIAS_INDEX[_norm_text(_a)] = _d.code

_EXCLUDES: dict[str, tuple[str, ...]] = {d.code: tuple(_norm_text(e) for e in d.excludes) for d in _DEFS}

# 比值项: 「比值/比率/比例/…比(」「A与B比」; 「比色法」「比浊法」「比重」不是比值
_CN_RATIO_RE = re.compile(r"比(?![色浊重])")
# 名字里夹带的单位 (「LDL-C mmol/L」「肌酐(μmol/L)」): 先剥掉再判比值, 单位里的「/」不是比值
_UNIT_BASE = r"(?:[mμunp]?mol|[mμunp]?g|i?u|ml|10\^?\d+|10e\d+)"
_UNIT_TOKEN_RE = re.compile(rf"\({_UNIT_BASE}/[^)]*\)|(?<![a-z0-9]){_UNIT_BASE}/[a-z0-9.^*/]*")


def _is_word_char(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _occurs(alias: str, name: str) -> bool:
    """alias 出现在 name 中, 且其 ASCII 字母数字端点不与相邻 ASCII 字母数字相连。

    「ldl」∉「vldl-c」、「cr」∉「hs-crp」、「tg」∉「tgab」、「tc」∉「qtc」、「hb」∉「hbsag」。
    中文没有词边界, 中文端点的误配 (「极低密度…」「尿肌酐」) 由各定义的 excludes 挡。
    """
    start = name.find(alias)
    while start != -1:
        end = start + len(alias)
        left_ok = not (_is_word_char(alias[0]) and start > 0 and _is_word_char(name[start - 1]))
        right_ok = not (_is_word_char(alias[-1]) and end < len(name) and _is_word_char(name[end]))
        if left_ok and right_ok:
            return True
        start = name.find(alias, start + 1)
    return False


# 负荷后/定时血糖: 前面不能再有数字 (「12h」是禁食时长, 不是 2h 时间点)
_GLUCOSE_TIMEPOINT_RE = re.compile(r"(?<![0-9.])(?:0\.5|1|2|3)\s*(?:h|hr|小时)|(?<![0-9])(?:30|60|120|180)\s*(?:min|分钟)")


_OGTT_MARKERS = ("ogtt", "糖耐", "tolerance")


def _excluded(code: str, key: str) -> bool:
    # 去空格只用于中文排除词 (「尿 肌酐」「尿 尿酸」); 英文去空格会粘词: plasmacreatinine 含 acr
    compact = key.replace(" ", "")
    if code == "glucose_fasting":
        if _GLUCOSE_TIMEPOINT_RE.search(key):
            return True
        fasting = "空腹" in key or "fasting" in key  # OGTT 的空腹点仍是空腹血糖
    for ex in _EXCLUDES[code]:
        if code == "glucose_fasting" and fasting and ex in _OGTT_MARKERS:
            continue
        if ex in key or (not ex.isascii() and ex in compact):
            return True
    return False


def _core(key: str) -> str:
    """剥掉名字里的单位片段后的项目名 (剥空了就用原名)。"""
    return re.sub(r"\s+", " ", _UNIT_TOKEN_RE.sub(" ", key)).strip() or key


def _is_ratio(core: str) -> bool:
    return bool(_CN_RATIO_RE.search(core)) or _occurs("ratio", core) or "/" in core


def _match(key: str) -> Optional[str]:
    code = _ALIAS_INDEX.get(key)
    if code is not None and not _excluded(code, key):
        return code
    # 包含匹配 (中文项目名常带前后缀): 边界感知, 取最长 (最具体) 的未被排除别名
    best_len, best_code = 0, None
    for alias, code in _ALIAS_INDEX.items():
        if len(alias) > best_len and _occurs(alias, key) and not _excluded(code, key):
            best_len, best_code = len(alias), code
    return best_code


def resolve_code(name_or_code: str) -> Optional[str]:
    """把任意项目名/别名/code 解析成 canonical code; 解析不到返回 None。

    安全敏感 —— biomarker code 喂给 Safety Guardian / Twin / 干预周期, 误判会污染序列:
      1. 比值/比例类名字 → None; 名字含「/」(尿素氮/肌酐、LDL-C/HDL-C) 只有各段解析为同一 code 才接受
         (「肌酐/CREA」「ALT/GPT」)。名字里夹带的单位 (「LDL-C mmol/L」) 先剥掉。
      2. 精确别名, 否则边界感知的包含匹配取最长别名 (_occurs); 永不做「名字 ⊆ 别名」的反向匹配。
      3. 名字含该定义任一排除词 → 该定义不参与 (「极低密度脂蛋白-C」不是 LDL, 「尿肌酐」不是肌酐)。
    不再退化到 exam_packages.normalize_item_name: 它的反向包含 + 无边界子串正是事故来源。
    """
    key = _norm_text(name_or_code)
    if not key:
        return None
    core = _core(key)
    if _CN_RATIO_RE.search(core) or _occurs("ratio", core):
        return None
    if "/" in core:
        codes = {_match(part.strip()) for part in core.split("/") if part.strip()}
        return codes.pop() if len(codes) == 1 and None not in codes else None
    return _match(core)


def name_conflicts_with_code(name: Optional[str], code: str) -> bool:
    """项目名是否明确指向 code 以外的东西 (校验 OCR/LLM 给的 item_code 提示、Safety 关键字兜底)。

    冲突 = 命中 code 的排除词、是比值, 或解析成另一个 registry code。解析不出 (None) 不算冲突:
    名字可能只是别名表没收录 (如英文全称), 这时保留提示。
    """
    key = _norm_text(name)
    if code not in REGISTRY or not key:
        return False
    if _excluded(code, key):
        return True
    resolved = resolve_code(key)
    if _is_ratio(_core(key)):  # 比值: 只有各段都指向 code (「肌酐/CREA」) 才不冲突
        return resolved != code
    return resolved is not None and resolved != code


def get_definition(name_or_code: str) -> Optional[BiomarkerDefinition]:
    code = name_or_code if name_or_code in REGISTRY else resolve_code(name_or_code)
    return REGISTRY.get(code) if code else None


def _unit_factor(defn: BiomarkerDefinition, u: str) -> Optional[float]:
    """归一后的单位 → 换算到 canonical 的乘数; None = 不可线性换算 (HbA1c 的 mmol/mol 在调用方特判)。"""
    if not u or u == _norm_unit(defn.canonical_unit):
        return 1.0
    if u in defn.unit_conversions:
        return defn.unit_conversions[u]
    if defn.code == "egfr" and u.startswith(("ml/min", "ml/分")):  # ml/min、ml/min/1.73m2、mL/min/{1.73_m2}…
        return 1.0
    if defn.code == "egfr" and u.startswith("ml/s"):
        return 60.0
    return None


def has_unit(unit: Optional[str]) -> bool:
    return bool(_norm_unit(unit))


def unit_status(defn: BiomarkerDefinition, unit: Optional[str]) -> str:
    """'ok' 可换算 (含缺单位) / 'incompatible' 已识别但量纲不符 / 'unknown' 未识别写法。"""
    u = _norm_unit(unit)
    if _unit_factor(defn, u) is not None or (defn.code == "glucose_hba1c" and u == "mmol/mol"):
        return "ok"
    if u in _KNOWN_UNITS or u.startswith(_FLOW_PREFIXES):
        return "incompatible"
    return "unknown"


def to_canonical_unit(defn: BiomarkerDefinition, value: float, unit: Optional[str]) -> tuple[float, str]:
    """把 (value, unit) 换算到 canonical_unit。不可换算的单位原样返回 (调用方按 unit_status 决定是否采信)。"""
    u = _norm_unit(unit)
    # HbA1c 特例: IFCC mmol/mol → NGSP %
    if defn.code == "glucose_hba1c" and u == "mmol/mol":
        return round(value / 10.929 + 2.15, 2), defn.canonical_unit
    factor = _unit_factor(defn, u)
    if factor == 1.0:
        return value, defn.canonical_unit
    if factor is not None:
        return round(value * factor, 3), defn.canonical_unit
    return value, unit or defn.canonical_unit
