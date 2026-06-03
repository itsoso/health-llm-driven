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
"""
from __future__ import annotations

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
    # 其它单位(小写, 去空格) -> 乘以该系数得到 canonical_unit 值
    unit_conversions: dict = field(default_factory=dict)
    # True: 偏高为风险(LDL/TG/尿酸/肝酶...); False: 偏低为风险(HDL/eGFR)
    higher_is_risk: bool = True

    def resolve_range(self, sex: Optional[str], age: Optional[int]) -> Optional[RefRange]:
        # 先找最具体(性别匹配)的, 再退化到通用.
        specific = [r for r in self.ref_ranges if r.sex == sex and r.matches(sex, age)]
        if specific:
            return specific[0]
        generic = [r for r in self.ref_ranges if r.matches(sex, age)]
        return generic[0] if generic else None


def _norm_unit(u: Optional[str]) -> str:
    return (u or "").strip().lower().replace(" ", "").replace("·", "/")


# ── 代谢健康 MVP 面板 ─────────────────────────────────────
_DEFS: tuple[BiomarkerDefinition, ...] = (
    # 血脂
    BiomarkerDefinition(
        code="lipid_ldl", display="低密度脂蛋白胆固醇", domain="lipid", canonical_unit="mmol/L",
        aliases=("低密度脂蛋白", "低密度脂蛋白胆固醇", "LDL", "LDL-C", "LDL-胆固醇", "LDLC"),
        ref_ranges=(RefRange(high=3.4),),
        unit_conversions={"mg/dl": 1 / 38.67},
        higher_is_risk=True,
    ),
    BiomarkerDefinition(
        code="lipid_hdl", display="高密度脂蛋白胆固醇", domain="lipid", canonical_unit="mmol/L",
        aliases=("高密度脂蛋白", "高密度脂蛋白胆固醇", "HDL", "HDL-C", "HDLC"),
        ref_ranges=(RefRange(low=1.0, sex="male"), RefRange(low=1.3, sex="female"), RefRange(low=1.0)),
        unit_conversions={"mg/dl": 1 / 38.67},
        higher_is_risk=False,  # 偏低为风险
    ),
    BiomarkerDefinition(
        code="lipid_tg", display="甘油三酯", domain="lipid", canonical_unit="mmol/L",
        aliases=("甘油三酯", "三酰甘油", "TG", "TRIG"),
        ref_ranges=(RefRange(high=1.7),),
        unit_conversions={"mg/dl": 1 / 88.57},
        higher_is_risk=True,
    ),
    BiomarkerDefinition(
        code="lipid_tc", display="总胆固醇", domain="lipid", canonical_unit="mmol/L",
        aliases=("总胆固醇", "胆固醇", "TC", "CHOL", "TCHO"),
        ref_ranges=(RefRange(high=5.2),),
        unit_conversions={"mg/dl": 1 / 38.67},
        higher_is_risk=True,
    ),
    # 血糖
    BiomarkerDefinition(
        code="glucose_fasting", display="空腹血糖", domain="glucose", canonical_unit="mmol/L",
        aliases=("空腹血糖", "葡萄糖", "血糖", "GLU", "FBG", "GLU-F"),
        ref_ranges=(RefRange(low=3.9, high=6.1),),
        unit_conversions={"mg/dl": 1 / 18.0},
        higher_is_risk=True,
    ),
    BiomarkerDefinition(
        code="glucose_hba1c", display="糖化血红蛋白", domain="glucose", canonical_unit="%",
        aliases=("糖化血红蛋白", "糖化血红蛋白测定", "糖化", "HbA1c", "GHb", "A1C"),
        ref_ranges=(RefRange(high=5.7),),
        # IFCC mmol/mol → NGSP%: %≈mmol/mol/10.929+2.15; 用近似线性系数 + 偏移在 normalize 里特判
        unit_conversions={},
        higher_is_risk=True,
    ),
    # 肝功能
    BiomarkerDefinition(
        code="ALT", display="谷丙转氨酶", domain="liver", canonical_unit="U/L",
        aliases=("ALT", "谷丙转氨酶", "丙氨酸氨基转移酶", "丙氨酸转氨酶"),
        ref_ranges=(RefRange(high=50, sex="male"), RefRange(high=40, sex="female"), RefRange(high=50)),
        higher_is_risk=True,
    ),
    BiomarkerDefinition(
        code="AST", display="谷草转氨酶", domain="liver", canonical_unit="U/L",
        aliases=("AST", "谷草转氨酶", "天门冬氨酸氨基转移酶", "天冬氨酸氨基转移酶"),
        ref_ranges=(RefRange(high=40),),
        higher_is_risk=True,
    ),
    BiomarkerDefinition(
        code="GGT", display="谷氨酰转肽酶", domain="liver", canonical_unit="U/L",
        aliases=("GGT", "γ-谷氨酰转肽酶", "谷氨酰转肽酶", "γ-GT", "r-GT"),
        ref_ranges=(RefRange(high=60, sex="male"), RefRange(high=45, sex="female"), RefRange(high=60)),
        higher_is_risk=True,
    ),
    # 肾功能
    BiomarkerDefinition(
        code="CREA", display="肌酐", domain="kidney", canonical_unit="µmol/L",
        aliases=("肌酐", "血肌酐", "CREA", "Cr", "SCr"),
        ref_ranges=(RefRange(low=57, high=97, sex="male"), RefRange(low=41, high=73, sex="female"),
                    RefRange(low=44, high=106)),
        unit_conversions={"mg/dl": 88.4},
        higher_is_risk=True,
    ),
    BiomarkerDefinition(
        code="egfr", display="估算肾小球滤过率", domain="kidney", canonical_unit="mL/min/1.73m²",
        aliases=("eGFR", "估算肾小球滤过率", "肾小球滤过率", "GFR"),
        ref_ranges=(RefRange(low=90),),
        higher_is_risk=False,  # 偏低为风险
    ),
    BiomarkerDefinition(
        code="UA", display="尿酸", domain="metabolic", canonical_unit="µmol/L",
        aliases=("尿酸", "血尿酸", "UA", "URIC"),
        ref_ranges=(RefRange(low=208, high=428, sex="male"), RefRange(low=155, high=357, sex="female"),
                    RefRange(low=155, high=428)),
        unit_conversions={"mg/dl": 59.48},
        higher_is_risk=True,
    ),
    BiomarkerDefinition(
        code="BUN", display="尿素氮", domain="kidney", canonical_unit="mmol/L",
        aliases=("尿素氮", "尿素", "BUN", "UREA"),
        ref_ranges=(RefRange(low=2.9, high=8.2),),
        unit_conversions={"mg/dl": 1 / 2.8},
        higher_is_risk=True,
    ),
)

# code -> def
REGISTRY: dict[str, BiomarkerDefinition] = {d.code: d for d in _DEFS}

# 别名(小写) -> code; 同时把 code 自身、display 也并入.
_ALIAS_INDEX: dict[str, str] = {}
for _d in _DEFS:
    _ALIAS_INDEX[_d.code.lower()] = _d.code
    _ALIAS_INDEX[_d.display.lower()] = _d.code
    for _a in _d.aliases:
        _ALIAS_INDEX[_a.strip().lower()] = _d.code


def resolve_code(name_or_code: str) -> Optional[str]:
    """把任意项目名/别名/code 解析成 canonical code; 解析不到返回 None。

    先查本注册表别名索引 (精确 + 包含), 再退化到 exam_packages.normalize_item_name。
    """
    if not name_or_code:
        return None
    key = name_or_code.strip().lower()
    if key in _ALIAS_INDEX:
        return _ALIAS_INDEX[key]
    # 包含匹配 (中文项目名常带前后缀)
    for alias, code in _ALIAS_INDEX.items():
        if alias and (alias in key or key in alias):
            return code
    # 退化到既有别名表
    try:
        from app.services.exam_packages import normalize_item_name
        code, _label = normalize_item_name(name_or_code)
        if code and code in REGISTRY:
            return code
    except Exception:
        pass
    return None


def get_definition(name_or_code: str) -> Optional[BiomarkerDefinition]:
    code = name_or_code if name_or_code in REGISTRY else resolve_code(name_or_code)
    return REGISTRY.get(code) if code else None


def to_canonical_unit(defn: BiomarkerDefinition, value: float, unit: Optional[str]) -> tuple[float, str]:
    """把 (value, unit) 换算到 canonical_unit。未知单位则假定已是 canonical。"""
    u = _norm_unit(unit)
    cu = _norm_unit(defn.canonical_unit)
    if not u or u == cu:
        return value, defn.canonical_unit
    # HbA1c 特例: IFCC mmol/mol → NGSP %
    if defn.code == "glucose_hba1c" and u in ("mmol/mol", "mmolmol"):
        return round(value / 10.929 + 2.15, 2), defn.canonical_unit
    factor = defn.unit_conversions.get(u)
    if factor is not None:
        return round(value * factor, 3), defn.canonical_unit
    # 未知单位: 不强转, 标记仍用原单位 (由 normalize 降低 confidence)
    return value, unit or defn.canonical_unit
