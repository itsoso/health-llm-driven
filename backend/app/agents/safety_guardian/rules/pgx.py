"""
药物基因组学规则 (PGx)。

匹配用户基因组中的关键位点与在服药物，给出个体化剂量/选择建议。
数据来源：CPIC (Clinical Pharmacogenetics Implementation Consortium) 指南。

规则覆盖的基因：
  CYP2D6, CYP2C19, CYP2C9, VKORC1, SLCO1B1, G6PD, HLA-B*57:01,
  DPYD, TPMT, UGT1A1, ALDH2, MTHFR

每条规则只在（a）用户基因有该位点 AND（b）用户在服相关药物时触发。
"""

from typing import Any, Dict, List, Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.rules.ddi import _has_drug_class, _med_names
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin


# ─────────────────────── 基因查找工具 ──────────────────


def _find_variant_by_gene(twin: HealthTwin, gene_name: str) -> Optional[Dict[str, Any]]:
    """在 twin.genetic 的三个分类里找某基因的变异。"""
    pools = (
        twin.genetic.drug_sensitivity,
        twin.genetic.risk_variants,
        twin.genetic.protective_variants,
    )
    for pool in pools:
        for v in pool or []:
            name = (v.get("gene_name") or "").strip().upper()
            if name == gene_name.upper():
                return v
    return None


def _is_poor_metabolizer(variant: Dict[str, Any]) -> bool:
    """启发式判断 PM（poor metabolizer）。看 result_label + genotype。"""
    if not variant:
        return False
    label = (variant.get("result_label") or "").lower()
    geno = (variant.get("genotype") or "").lower()
    keywords = ["poor", "pm", "慢代谢", "弱代谢", "代谢差"]
    return any(k in label for k in keywords) or any(k in geno for k in keywords)


def _is_ultra_rapid_metabolizer(variant: Dict[str, Any]) -> bool:
    if not variant:
        return False
    label = (variant.get("result_label") or "").lower()
    geno = (variant.get("genotype") or "").lower()
    keywords = ["ultra", "um", "超快代谢", "快代谢", "ultrarapid"]
    return any(k in label for k in keywords) or any(k in geno for k in keywords)


def _is_deficient_or_risk(variant: Dict[str, Any]) -> bool:
    if not variant:
        return False
    label = (variant.get("result_label") or "").lower()
    risk = (variant.get("risk_level") or "").lower()
    keys = ["deficient", "deficiency", "缺陷", "缺乏", "risk", "高风险", "中风险"]
    return any(k in label for k in keys) or any(k in risk for k in keys)


# ─────────────────────── CYP2D6 × 可待因/曲马多 ──────


@register
def pgx_cyp2d6_opioid(twin: HealthTwin) -> Optional[Alert]:
    """
    CYP2D6 PM: 可待因/曲马多无效
    CYP2D6 UM: 转化过快，吗啡毒性
    """
    variant = _find_variant_by_gene(twin, "CYP2D6")
    if not variant:
        return None

    meds = _med_names(twin)
    target_meds = [m for m in meds if any(k in m for k in ["可待因", "codeine", "曲马多", "tramadol"])]
    if not target_meds:
        return None

    if _is_poor_metabolizer(variant):
        return Alert(
            rule_id="pgx.cyp2d6_opioid_pm",
            category="pgx",
            severity=Severity.HIGH,
            title="CYP2D6 慢代谢 —— 可待因/曲马多无效",
            message=(
                f"你的 CYP2D6 基因型 ({variant.get('genotype')}) 提示慢代谢/poor metabolizer。"
                "可待因需要 CYP2D6 转化为吗啡才能镇痛，PM 人群使用基本无效。"
                f"你当前在用：{', '.join(target_meds)}。"
            ),
            action="与处方医生讨论换用非 CYP2D6 依赖的镇痛药（扑热息痛、布洛芬、非可待因类阿片如羟考酮）。",
            data_citation={"variant": variant, "meds": target_meds},
            references=[
                "https://cpicpgx.org/guidelines/guideline-for-codeine-and-cyp2d6/",
            ],
        )

    if _is_ultra_rapid_metabolizer(variant):
        return Alert(
            rule_id="pgx.cyp2d6_opioid_um",
            category="pgx",
            severity=Severity.CRITICAL,
            title="CYP2D6 超快代谢 —— 可待因中毒风险",
            message=(
                f"你的 CYP2D6 基因型 ({variant.get('genotype')}) 提示超快代谢/UM。"
                "UM 人群使用可待因/曲马多会在体内迅速形成高浓度吗啡，"
                "可能发生致命呼吸抑制，这是 FDA 黑框警示内容。"
            ),
            action="绝对避免使用可待因和曲马多；选择非 CYP2D6 代谢的镇痛药（扑热息痛、布洛芬、吗啡直接使用、羟考酮）。",
            data_citation={"variant": variant, "meds": target_meds},
            references=[
                "https://www.fda.gov/drugs/drug-safety-and-availability/fda-restricts-use-prescription-cough-medicines-containing-codeine-or-hydrocodone",
            ],
            requires_medical_attention=True,
        )

    return None


# ─────────────────────── CYP2C19 × 氯吡格雷 ──────────


@register
def pgx_cyp2c19_clopidogrel(twin: HealthTwin) -> Optional[Alert]:
    """CYP2C19 PM: 氯吡格雷无法活化，抗血小板作用显著减弱。"""
    variant = _find_variant_by_gene(twin, "CYP2C19")
    if not variant or not _is_poor_metabolizer(variant):
        return None

    meds = _med_names(twin)
    clopi = [m for m in meds if "氯吡格雷" in m or "clopidogrel" in m]
    if not clopi:
        return None

    return Alert(
        rule_id="pgx.cyp2c19_clopidogrel",
        category="pgx",
        severity=Severity.HIGH,
        title="CYP2C19 慢代谢 —— 氯吡格雷可能无效",
        message=(
            f"你的 CYP2C19 基因型 ({variant.get('genotype')}) 提示慢代谢。"
            "氯吡格雷是前体药，需要 CYP2C19 转化为活性代谢物才能抗血小板。"
            "PM 人群使用氯吡格雷的心血管事件风险显著高于普通人群。"
        ),
        action="与处方医生讨论换用替格瑞洛 (Ticagrelor) 或普拉格雷 (Prasugrel)，这两种不依赖 CYP2C19。",
        data_citation={"variant": variant, "meds": clopi},
        references=[
            "https://cpicpgx.org/guidelines/guideline-for-clopidogrel-and-cyp2c19/",
        ],
        requires_medical_attention=True,
    )


# ─────────────────────── CYP2C9 + VKORC1 × 华法林 ────


@register
def pgx_warfarin_dosing(twin: HealthTwin) -> Optional[Alert]:
    """CYP2C9 和 VKORC1 决定华法林剂量敏感度。"""
    meds = _med_names(twin)
    warf = [m for m in meds if "华法林" in m or "warfarin" in m]
    if not warf:
        return None

    cyp2c9 = _find_variant_by_gene(twin, "CYP2C9")
    vkorc1 = _find_variant_by_gene(twin, "VKORC1")
    if not (cyp2c9 or vkorc1):
        return None

    sensitive = _is_poor_metabolizer(cyp2c9) or _is_deficient_or_risk(vkorc1)
    if not sensitive:
        return None

    return Alert(
        rule_id="pgx.warfarin_cyp2c9_vkorc1",
        category="pgx",
        severity=Severity.HIGH,
        title="华法林剂量基因敏感",
        message=(
            f"你的 CYP2C9 ({cyp2c9.get('genotype') if cyp2c9 else 'N/A'}) 或 VKORC1 "
            f"({vkorc1.get('genotype') if vkorc1 else 'N/A'}) 变异提示对华法林剂量敏感，"
            "标准起始剂量可能过高，INR 容易超标。"
        ),
        action="处方医生应基于基因型调整起始剂量（参考 warfarindosing.org），起始后 3-5 天密切监测 INR。",
        data_citation={"cyp2c9": cyp2c9, "vkorc1": vkorc1, "warfarin": warf},
        references=[
            "https://cpicpgx.org/guidelines/guideline-for-warfarin-and-cyp2c9-and-vkorc1/",
        ],
        requires_medical_attention=True,
    )


# ─────────────────────── SLCO1B1 × 辛伐他汀 ─────────


@register
def pgx_slco1b1_simvastatin(twin: HealthTwin) -> Optional[Alert]:
    """SLCO1B1*5 (521T>C) → 辛伐他汀肌病风险升高 3-5 倍。"""
    variant = _find_variant_by_gene(twin, "SLCO1B1")
    if not variant or not _is_deficient_or_risk(variant):
        return None

    meds = _med_names(twin)
    simva = [m for m in meds if "辛伐他汀" in m or "simvastatin" in m]
    if not simva:
        return None

    return Alert(
        rule_id="pgx.slco1b1_simvastatin",
        category="pgx",
        severity=Severity.HIGH,
        title="SLCO1B1 变异 —— 辛伐他汀肌病风险",
        message=(
            f"你的 SLCO1B1 基因型 ({variant.get('genotype')}) 提示辛伐他汀的肝脏摄取减弱，"
            "血药浓度升高，肌病和横纹肌溶解风险提高 3-5 倍（以高剂量尤甚）。"
        ),
        action=(
            "与医生讨论降低剂量（≤20mg/日）或换用普伐他汀、瑞舒伐他汀（SLCO1B1 影响较小）；"
            "任何肌肉痛、无力、尿色变深立即停药就医。"
        ),
        data_citation={"variant": variant, "meds": simva},
        references=[
            "https://cpicpgx.org/guidelines/guideline-for-simvastatin-and-slco1b1/",
        ],
        requires_medical_attention=True,
    )


# ─────────────────────── G6PD × 禁忌药物 ─────────────


@register
def pgx_g6pd_contraindicated(twin: HealthTwin) -> Optional[Alert]:
    """G6PD 缺陷 → 禁用氧化应激类药物（伯氨喹、硝基呋喃妥因、磺胺、大剂量维 C 等）。"""
    variant = _find_variant_by_gene(twin, "G6PD")
    if not variant or not _is_deficient_or_risk(variant):
        return None

    meds = _med_names(twin)
    contra = [
        m for m in meds if any(
            k in m for k in [
                "伯氨喹", "primaquine", "硝基呋喃妥因", "nitrofurantoin",
                "磺胺", "sulfa", "达普松", "dapsone", "甲基蓝", "methylene blue",
            ]
        )
    ]
    if not contra:
        return Alert(
            rule_id="pgx.g6pd_info",
            category="pgx",
            severity=Severity.INFO,
            title="G6PD 缺陷 —— 用药禁忌清单",
            message=(
                f"你的 G6PD 基因型 ({variant.get('genotype')}) 提示酶活性降低。"
                "此状态禁用或慎用：伯氨喹、硝基呋喃妥因、磺胺类抗生素、达普松、"
                "萘、甲基蓝、大剂量维生素 C、蚕豆（蚕豆病）。"
            ),
            action="就诊时主动告知医生你的 G6PD 状态；避免蚕豆、樟脑丸接触；购药前检查说明书。",
            data_citation={"variant": variant},
            references=["https://cpicpgx.org/guidelines/cpic-guideline-for-rasburicase-and-g6pd/"],
        )

    return Alert(
        rule_id="pgx.g6pd_contraindicated",
        category="pgx",
        severity=Severity.CRITICAL,
        title="G6PD 缺陷与禁忌药物同时存在",
        message=(
            f"你的 G6PD 酶活性降低 ({variant.get('genotype')}) 且在服用可诱发急性溶血的药物："
            f"{', '.join(contra)}。严重情况下会发生血管内溶血、急性肾损伤。"
        ),
        action="立即停药并联系处方医生换药；出现茶色尿、黄疸、乏力、心悸请急诊。",
        data_citation={"variant": variant, "meds": contra},
        requires_medical_attention=True,
    )


# ─────────────────────── HLA-B*57:01 × 阿巴卡韦 ──────


@register
def pgx_hla_b5701_abacavir(twin: HealthTwin) -> Optional[Alert]:
    """HLA-B*57:01 阳性 → 阿巴卡韦禁忌 (FDA 黑框, 超敏综合征)。"""
    variant = _find_variant_by_gene(twin, "HLA-B") or _find_variant_by_gene(twin, "HLA-B*5701")
    if not variant:
        return None
    label = (variant.get("result_label") or "").lower() + (variant.get("genotype") or "").lower()
    if "57:01" not in label and "5701" not in label:
        return None

    meds = _med_names(twin)
    abacavir = [m for m in meds if "阿巴卡韦" in m or "abacavir" in m]

    sev = Severity.CRITICAL if abacavir else Severity.INFO
    title = "HLA-B*57:01 阳性，禁用阿巴卡韦" if abacavir else "HLA-B*57:01 阳性（阿巴卡韦禁忌）"

    return Alert(
        rule_id="pgx.hla_b5701_abacavir",
        category="pgx",
        severity=sev,
        title=title,
        message=(
            "HLA-B*57:01 阳性携带者使用阿巴卡韦会出现致命的超敏综合征。"
            + (f"你当前在服用 {', '.join(abacavir)}。" if abacavir else "这是终身避免的药物。")
        ),
        action=(
            "立即停药并联系 HIV 科医生更换抗病毒方案；如已出现发热/皮疹/呼吸道症状立即急诊。"
            if abacavir
            else "就医时主动告知此基因型；避免所有含阿巴卡韦的固定复方制剂。"
        ),
        data_citation={"variant": variant, "meds": abacavir},
        references=["https://cpicpgx.org/guidelines/guideline-for-abacavir-and-hla-b/"],
        requires_medical_attention=bool(abacavir),
    )


# ─────────────────────── DPYD × 氟尿嘧啶 ────────────


@register
def pgx_dpyd_fluoropyrimidine(twin: HealthTwin) -> Optional[Alert]:
    """DPYD 缺陷 → 5-FU/卡培他滨严重毒性。"""
    variant = _find_variant_by_gene(twin, "DPYD")
    if not variant or not _is_deficient_or_risk(variant):
        return None

    meds = _med_names(twin)
    fp = [m for m in meds if any(k in m for k in ["氟尿嘧啶", "5-fu", "卡培他滨", "capecitabine"])]
    if not fp:
        return None

    return Alert(
        rule_id="pgx.dpyd_5fu",
        category="pgx",
        severity=Severity.CRITICAL,
        title="DPYD 缺陷 —— 氟尿嘧啶严重毒性风险",
        message=(
            f"DPYD 基因型 ({variant.get('genotype')}) 提示 DPD 酶活性降低，"
            "使用 5-FU/卡培他滨会积累并引发致命的骨髓抑制、黏膜炎、神经毒性。"
        ),
        action="立即联系肿瘤科医生；必须大幅减量或换药；CPIC 指南有明确的剂量调整方案。",
        data_citation={"variant": variant, "meds": fp},
        references=["https://cpicpgx.org/guidelines/guideline-for-fluoropyrimidines-and-dpyd/"],
        requires_medical_attention=True,
    )


# ─────────────────────── ALDH2 × 酒精 ────────────────


@register
def pgx_aldh2_alcohol(twin: HealthTwin) -> Optional[Alert]:
    """ALDH2*2/*2 或 *1/*2 → 醛类代谢受阻，饮酒高风险（面红、癌症、心脑血管）。"""
    variant = _find_variant_by_gene(twin, "ALDH2")
    if not variant:
        return None
    geno = (variant.get("genotype") or "").lower()
    label = (variant.get("result_label") or "").lower()
    is_risk = "*2" in geno or "缺陷" in label or "升高" in label or "risk" in label or _is_deficient_or_risk(variant)
    if not is_risk:
        return None

    return Alert(
        rule_id="pgx.aldh2_alcohol",
        category="pgx",
        severity=Severity.MEDIUM,
        title="ALDH2 变异 —— 饮酒高风险",
        message=(
            f"你的 ALDH2 基因型 ({variant.get('genotype')}) 使乙醛代谢显著受损。"
            "饮酒后乙醛蓄积会引发面红、心悸、头痛，并长期显著升高食管癌、胃癌、心血管疾病风险。"
        ),
        action=(
            "最安全的策略是完全戒酒。若确需社交饮酒，每周不超过 1-2 次少量，"
            "避免与抗氧化剂（如某些化疗药）同时使用。"
        ),
        data_citation={"variant": variant},
        references=[
            "https://www.cell.com/cell-metabolism/fulltext/S1550-4131(14)00384-2",
        ],
    )


# ─────────────────────── MTHFR × 叶酸代谢 ────────────


@register
def pgx_mthfr_folate(twin: HealthTwin) -> Optional[Alert]:
    """MTHFR 677TT / 1298CC → 甲基化能力下降，建议甲基叶酸而非合成叶酸。"""
    variant = _find_variant_by_gene(twin, "MTHFR")
    if not variant:
        return None
    geno = (variant.get("genotype") or "").upper()
    if not ("TT" in geno or "CC" in geno or _is_deficient_or_risk(variant)):
        return None

    return Alert(
        rule_id="pgx.mthfr_folate",
        category="pgx",
        severity=Severity.LOW,
        title="MTHFR 变异 —— 建议甲基叶酸形式",
        message=(
            f"你的 MTHFR 基因型 ({variant.get('genotype')}) 显示甲基化能力下降。"
            "普通合成叶酸（folic acid）需要 MTHFR 转化为活性 L-5-MTHF，此变异者转化效率较低。"
        ),
        action=(
            "叶酸补充建议直接使用甲基叶酸（L-5-MTHF / methyl folate）而非合成叶酸；"
            "配合维 B12（甲钴胺）和 B6 效果更好；检查同型半胱氨酸水平评估甲基化状态。"
        ),
        data_citation={"variant": variant},
    )
