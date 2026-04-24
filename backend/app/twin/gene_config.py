"""基因配置文件 — 将原始基因变异转化为结构化行动参数

每个用户的基因数据是不变的底层参数。本模块将 Twin.genetic 中的原始变异列表
转化为语义化配置，供所有 Specialist 直接消费，无需各自解析变异。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.twin.schema import HealthTwin


@dataclass
class GeneConfig:
    has_data: bool = False

    # 甲基化 (MTHFR C677T)
    methylation: str = "normal"  # normal | impaired | severely_impaired
    folate_form: str = "folic_acid"  # folic_acid | methylfolate

    # 脂质代谢 (APOE)
    apoe_type: Optional[str] = None  # e2/e3 | e3/e3 | e3/e4 | e4/e4
    saturated_fat_sensitivity: str = "normal"  # normal | high

    # Omega-3 转化 (FADS1)
    omega3_conversion: str = "normal"  # normal | reduced

    # 肥胖风险 (FTO)
    obesity_risk: str = "normal"  # normal | elevated

    # 乳糖耐受 (LCT/MCM6)
    lactose_tolerant: bool = True

    # 肌纤维类型 (ACTN3)
    muscle_type: str = "mixed"  # power | endurance | mixed

    # 炎症倾向 (IL-6, TNF-alpha)
    inflammation_tendency: str = "normal"  # normal | moderate | high

    # 抗氧化能力 (SOD2, GPX1, GSTP1)
    antioxidant_capacity: str = "normal"  # normal | reduced

    # 咖啡因代谢 (CYP1A2)
    caffeine_metabolism: str = "normal"  # fast | normal | slow

    # 酒精代谢 (ALDH2)
    alcohol_metabolism: str = "normal"  # normal | deficient

    # 心理特质 (COMT)
    stress_type: str = "mixed"  # warrior | worrier | mixed

    # 药物代谢概要
    drug_metabolism: Dict[str, str] = field(default_factory=dict)
    # e.g. {"CYP2D6": "poor", "CYP2C19": "rapid", "SLCO1B1": "reduced"}

    # 慢病相关
    salt_sensitivity: str = "normal"  # normal | high (ADD1)
    insulin_sensitivity: str = "normal"  # normal | reduced (PPARG)
    diabetes_risk: str = "normal"  # normal | elevated (TCF7L2)
    allergy_tendency: str = "normal"  # normal | elevated (IL-4/IL-13)

    # 运动损伤风险 (COL5A1)
    injury_risk: str = "normal"  # normal | elevated

    # 摘要（供 LLM prompt 注入）
    summary_lines: List[str] = field(default_factory=list)


def build_gene_config(twin: "HealthTwin") -> Optional[GeneConfig]:
    """从 Twin.genetic 构建结构化基因配置。无基因数据时返回 None。"""
    g = twin.genetic
    if not g.has_profile or g.total_variants == 0:
        return None

    cfg = GeneConfig(has_data=True)

    all_variants = (
        (g.drug_sensitivity or [])
        + (g.risk_variants or [])
        + (g.protective_variants or [])
        + (g.nutrition_variants or [])
        + (g.recovery_variants or [])
        + (g.exercise_variants or [])
        + (g.cognition_variants or [])
        + (g.personality_variants or [])
        + (g.sleep_variants or [])
    )

    by_gene: Dict[str, Dict[str, Any]] = {}
    for v in all_variants:
        name = (v.get("gene_name") or "").upper()
        if name:
            by_gene.setdefault(name, v)

    def _risk(name: str) -> bool:
        v = by_gene.get(name)
        if not v:
            return False
        label = (v.get("result_label") or "").lower()
        risk = (v.get("risk_level") or "").lower()
        geno = (v.get("genotype") or "").upper()
        return (
            "risk" in risk or "高" in risk or "中" in risk
            or "poor" in label or "reduced" in label
            or "TT" in geno
        )

    def _geno(name: str) -> str:
        v = by_gene.get(name)
        return (v.get("genotype") or "").upper() if v else ""

    def _label(name: str) -> str:
        v = by_gene.get(name)
        return (v.get("result_label") or "").lower() if v else ""

    # ── MTHFR ──
    mthfr_geno = _geno("MTHFR")
    if "TT" in mthfr_geno:
        cfg.methylation = "severely_impaired"
        cfg.folate_form = "methylfolate"
        cfg.summary_lines.append("MTHFR 677TT: 甲基化严重受损，必须使用甲基叶酸")
    elif "CT" in mthfr_geno or _risk("MTHFR"):
        cfg.methylation = "impaired"
        cfg.folate_form = "methylfolate"
        cfg.summary_lines.append("MTHFR 677CT: 甲基化能力下降，建议甲基叶酸")

    # ── APOE ──
    apoe = by_gene.get("APOE")
    if apoe:
        geno = _geno("APOE")
        cfg.apoe_type = geno if geno else None
        if "4" in geno:
            cfg.saturated_fat_sensitivity = "high"
            cfg.summary_lines.append(f"APOE {geno}: 饱和脂肪敏感，需严格控制LDL")

    # ── FADS1 ──
    if _risk("FADS1"):
        cfg.omega3_conversion = "reduced"
        cfg.summary_lines.append("FADS1: Omega-3转化效率低，需直接补充EPA/DHA")

    # ── FTO ──
    if _risk("FTO"):
        cfg.obesity_risk = "elevated"
        cfg.summary_lines.append("FTO: 肥胖风险升高，需高蛋白饮食+规律运动")

    # ── LCT/MCM6 ──
    lct = by_gene.get("LCT") or by_gene.get("MCM6")
    if lct and ("CC" in _geno("LCT") or "CC" in _geno("MCM6") or _risk("LCT")):
        cfg.lactose_tolerant = False
        cfg.summary_lines.append("LCT: 乳糖不耐受，避免直接饮用牛奶")

    # ── ACTN3 ──
    actn3_geno = _geno("ACTN3")
    if "XX" in actn3_geno or "TT" in actn3_geno:
        cfg.muscle_type = "endurance"
        cfg.summary_lines.append("ACTN3 XX: 慢肌纤维优势，适合耐力训练")
    elif "RR" in actn3_geno or "CC" in actn3_geno:
        cfg.muscle_type = "power"
        cfg.summary_lines.append("ACTN3 RR: 快肌纤维优势，适合爆发力训练")

    # ── 炎症 (IL-6, TNF) ──
    il6_risk = _risk("IL-6") or _risk("IL6")
    tnf_risk = _risk("TNF") or _risk("TNF-ALPHA") or _risk("TNFA")
    if il6_risk and tnf_risk:
        cfg.inflammation_tendency = "high"
        cfg.summary_lines.append("IL-6+TNF: 高炎症倾向，需抗炎饮食和充足恢复")
    elif il6_risk or tnf_risk:
        cfg.inflammation_tendency = "moderate"

    # ── 抗氧化 (SOD2, GPX1, GSTP1) ──
    sod2_risk = _risk("SOD2")
    gpx1_risk = _risk("GPX1")
    if sod2_risk or gpx1_risk:
        cfg.antioxidant_capacity = "reduced"
        cfg.summary_lines.append("SOD2/GPX1: 抗氧化能力下降，补充CoQ10和抗氧化食物")

    # ── CYP1A2 (咖啡因) ──
    cyp1a2 = by_gene.get("CYP1A2")
    if cyp1a2:
        label = _label("CYP1A2")
        if "slow" in label or "poor" in label:
            cfg.caffeine_metabolism = "slow"
            cfg.summary_lines.append("CYP1A2: 咖啡因慢代谢，下午后避免咖啡")
        elif "fast" in label or "ultra" in label:
            cfg.caffeine_metabolism = "fast"

    # ── ALDH2 (酒精) ──
    aldh2 = by_gene.get("ALDH2")
    if aldh2 and ((aldh2.get("risk_level") or "").lower() in ("medium", "high") or _risk("ALDH2")):
        cfg.alcohol_metabolism = "deficient"
        cfg.summary_lines.append("ALDH2: 酒精代谢缺陷，严格限酒")

    # ── COMT (心理) ──
    comt = by_gene.get("COMT")
    if comt:
        label = _label("COMT")
        geno = _geno("COMT")
        if "warrior" in label or "VAL/VAL" in geno:
            cfg.stress_type = "warrior"
        elif "worrier" in label or "MET/MET" in geno:
            cfg.stress_type = "worrier"
            cfg.summary_lines.append("COMT Met/Met: 焦虑敏感型，需正念和低咖啡因")

    # ── 药物代谢 ──
    for enzyme in ["CYP2D6", "CYP2C19", "CYP2C9", "SLCO1B1"]:
        v = by_gene.get(enzyme)
        if v:
            label = _label(enzyme)
            if "poor" in label:
                cfg.drug_metabolism[enzyme] = "poor"
            elif "ultra" in label or "rapid" in label:
                cfg.drug_metabolism[enzyme] = "rapid"
            elif "intermediate" in label:
                cfg.drug_metabolism[enzyme] = "intermediate"
            else:
                cfg.drug_metabolism[enzyme] = "normal"

    # ── 慢病相关 ──
    if _risk("ADD1"):
        cfg.salt_sensitivity = "high"
        cfg.summary_lines.append("ADD1: 盐敏感性高，每日钠摄入<2g")

    if _risk("PPARG"):
        cfg.insulin_sensitivity = "reduced"

    if _risk("TCF7L2"):
        cfg.diabetes_risk = "elevated"
        cfg.summary_lines.append("TCF7L2: 2型糖尿病风险升高，严格控糖")

    if _risk("IL-4") or _risk("IL4") or _risk("IL-13") or _risk("IL13"):
        cfg.allergy_tendency = "elevated"
        cfg.summary_lines.append("IL-4/IL-13: 过敏体质倾向，注意环境管理")

    # ── COL5A1 损伤 ──
    if _risk("COL5A1"):
        cfg.injury_risk = "elevated"
        cfg.summary_lines.append("COL5A1: 软组织损伤风险升高，充分热身")

    return cfg
