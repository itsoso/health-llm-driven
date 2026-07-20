"""
药物-药物相互作用规则 (DDI)。

聚焦用户当前在服药物：
- 替尔泊肽 Tirzepatide (GLP-1/GIP)
- 盐酸西替利嗪片 Cetirizine (二代抗组胺)
- 糠酸莫米松鼻喷雾剂 Mometasone Nasal (局部糖皮质激素)
- AKK 益生菌 (Akkermansia muciniphila)
+ 用户自报或数据库里其他潜在药物

每条规则做两件事：
- 精确 pattern match（药名关键字）
- 必要时考虑剂量/给药途径（例如莫米松鼻喷是局部用药，相互作用风险低）

规则格式参考：FDA 药品说明书 / Lexicomp / Micromedex 共识警示
"""

from typing import List, Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin


# ─────────────────────────── 药名关键字库 ─────────────────────────
# 单一事实源已抽到 app.services.drug_lexicon(SafetyGuardian 规则与 KB 对账处方 gate
# 共用,消除重复)。此处保留 DRUG_ALIASES 名字与语义,内容逐字节不变;新增/改药名去改
# drug_lexicon.DRUG_CLASS_ALIASES,对账 gate 会自动跟随。
from app.services.drug_lexicon import DRUG_CLASS_ALIASES as DRUG_ALIASES


def _med_names(twin: HealthTwin) -> List[str]:
    """从 Twin 提取在服药物名称小写列表（包括 notes 里提到的）。"""
    names: List[str] = []
    for m in twin.medication.active_meds or []:
        n = (m.get("name") or "").strip().lower()
        if n:
            names.append(n)
    return names


def _has_drug_class(med_names: List[str], class_key: str) -> List[str]:
    """返回匹配到某药物类的具体药名列表（空=未匹配）。"""
    aliases = DRUG_ALIASES.get(class_key, [])
    matched: List[str] = []
    for name in med_names:
        for alias in aliases:
            if alias.lower() in name:
                matched.append(name)
                break
    return matched


# ─────────────────────── GLP-1 × 磺脲/胰岛素 ─────────────────


@register
def ddi_glp1_hypoglycemia_risk(twin: HealthTwin) -> Optional[Alert]:
    """
    GLP-1 受体激动剂 + 胰岛素或磺脲类 → 低血糖风险显著升高。
    这是 FDA 黑框警示之一。
    """
    meds = _med_names(twin)
    glp1 = _has_drug_class(meds, "glp1")
    if not glp1:
        return None

    sulfa = _has_drug_class(meds, "sulfonylurea")
    ins = _has_drug_class(meds, "insulin")
    if not (sulfa or ins):
        return None

    combo = "磺脲类" if sulfa else "胰岛素"
    return Alert(
        rule_id="ddi.glp1_hypoglycemia",
        category="ddi",
        severity=Severity.HIGH,
        title=f"GLP-1 与{combo}合用 —— 低血糖风险升高",
        message=(
            f"你正在使用 GLP-1 药物（{', '.join(set(glp1))}）和{combo}"
            f"（{', '.join(set(sulfa + ins))}）。GLP-1 会增强胰岛素作用，"
            f"联合使用时低血糖发生率显著升高，尤其在餐前、运动后、空腹时。"
        ),
        action=(
            f"与处方医生确认是否需要减少{combo}剂量；"
            "随身准备快速碳水（葡萄糖片/果汁）；"
            "避免跳餐；家里常备血糖仪并在早晨、餐前、运动前后监测；"
            "出现出汗、震颤、心悸、意识模糊立即补糖。"
        ),
        data_citation={"glp1_meds": glp1, "combo_meds": sulfa + ins},
        references=[
            "https://www.fda.gov/drugs/drug-safety-and-availability",
        ],
        requires_medical_attention=True,
    )


# ─────────────────────── GLP-1 常识提示 ─────────────────


@register
def ddi_glp1_gastric_emptying_info(twin: HealthTwin) -> Optional[Alert]:
    """
    GLP-1 延迟胃排空 —— 对口服药物和补剂吸收有影响。信息级提示。
    """
    meds = _med_names(twin)
    glp1 = _has_drug_class(meds, "glp1")
    if not glp1:
        return None

    # 替尔泊肽是 GIP/GLP-1 双激动剂，避孕药暴露下降的证据仅见于替尔泊肽，
    # 不能外推到纯 GLP-1（司美格鲁肽对口服避孕药暴露无影响，Kapitza 2015 / FDA 说明书）。
    tirzepatide = [m for m in glp1 if "替尔泊肽" in m or "tirzepatide" in m]

    action_parts = [
        "左甲状腺素等窄治疗窗的口服药建议每天固定同一时段、空腹并与其他药物间隔服用，"
        "保持服药时间一致，并按医嘱定期复查 TSH（这一错开是按小时同日间隔，与 GLP-1 是否为注射日无关）",
        "正在使用华法林等抗凝药者，在 GLP-1 起始或调整剂量时按医嘱监测 INR",
    ]
    if tirzepatide:
        action_parts.append(
            "替尔泊肽（GIP/GLP-1）可能降低口服避孕药吸收，起始及每次加量后 4 周内"
            "建议加用屏障避孕法或改用非口服避孕方式"
        )
    action_parts.append("有疑问时咨询药师或处方医生")

    return Alert(
        rule_id="ddi.glp1_gastric_emptying",
        category="ddi",
        severity=Severity.LOW,
        title="GLP-1 会延迟胃排空",
        message=(
            f"你在使用 GLP-1 药物（{', '.join(set(glp1))}）。GLP-1 会减慢胃排空，"
            "可能使同时口服的药物吸收变慢、峰浓度（Cmax）略有下降，"
            "对吸收窗口狭窄或依赖稳定血药浓度的口服药（如左甲状腺素）可能有轻微影响。"
        ),
        action="；".join(action_parts) + "。",
        data_citation={"glp1_meds": glp1, "tirzepatide": tirzepatide},
    )


# ─────────────────────── 西替利嗪 × 中枢抑制剂 ─────────


@register
def ddi_cetirizine_cns_depressants(twin: HealthTwin) -> Optional[Alert]:
    """
    西替利嗪（二代抗组胺）与苯二氮䓬、阿片、一代抗组胺合用 → 累加中枢抑制。
    相比一代抗组胺，二代药嗜睡较轻，但仍非零。
    """
    meds = _med_names(twin)
    cet = _has_drug_class(meds, "cetirizine")
    if not cet:
        return None

    benzo = _has_drug_class(meds, "benzodiazepine")
    opio = _has_drug_class(meds, "opioid")
    fg_anti = _has_drug_class(meds, "first_gen_antihistamine")

    hits = benzo + opio + fg_anti
    if not hits:
        return None

    classes = []
    if benzo:
        classes.append("苯二氮䓬类")
    if opio:
        classes.append("阿片类")
    if fg_anti:
        classes.append("一代抗组胺")

    return Alert(
        rule_id="ddi.cetirizine_cns_depressants",
        category="ddi",
        severity=Severity.MEDIUM,
        title="西替利嗪与中枢抑制剂合用",
        message=(
            f"西替利嗪与{' / '.join(classes)}（{', '.join(set(hits))}）合用会叠加嗜睡、认知迟钝、"
            "跌倒风险，对驾驶、高空作业、机械操作有实际影响。"
        ),
        action=(
            "合用期间避免驾驶和需要警觉的活动；"
            "若主要是过敏控制需求，可考虑只保留一种药；"
            "老年人跌倒风险尤其值得关注。"
        ),
        data_citation={"cetirizine": cet, "concomitant": hits},
    )


# ─────────────────────── 华法林 × NSAID/抗血小板 ─────────


@register
def ddi_warfarin_bleeding_risk(twin: HealthTwin) -> Optional[Alert]:
    """华法林 + NSAID / 抗血小板 → 出血风险显著升高。"""
    meds = _med_names(twin)
    warf = _has_drug_class(meds, "warfarin")
    if not warf:
        return None

    nsaid = _has_drug_class(meds, "nsaid")
    antip = _has_drug_class(meds, "antiplatelet")

    concerning = nsaid + antip
    if not concerning:
        return None

    return Alert(
        rule_id="ddi.warfarin_bleeding",
        category="ddi",
        severity=Severity.HIGH,
        title="华法林与出血风险药物合用",
        message=(
            f"华法林 + {'NSAID' if nsaid else ''}{'/' if nsaid and antip else ''}{'抗血小板' if antip else ''}"
            f"（{', '.join(set(concerning))}）显著升高消化道和颅内出血风险。"
        ),
        action=(
            "尽快联系处方医生评估是否可用对乙酰氨基酚（扑热息痛）替代 NSAID；"
            "勤查 INR；警惕黑便、牙龈出血、皮下瘀斑、剧烈头痛等出血征兆。"
        ),
        data_citation={"warfarin": warf, "bleeding_risk_meds": concerning},
        references=["https://www.ahajournals.org/doi/10.1161/CIR.0000000000000643"],
        requires_medical_attention=True,
    )


# ─────────────────────── 他汀 × CYP3A4 强抑制剂 ─────────


@register
def ddi_statin_cyp3a4_inhibitor(twin: HealthTwin) -> Optional[Alert]:
    """辛伐他汀/阿托伐他汀 × CYP3A4 强抑制剂 → 肌病和横纹肌溶解风险。"""
    meds = _med_names(twin)
    statin = _has_drug_class(meds, "statin")
    if not statin:
        return None

    cyp_inh = _has_drug_class(meds, "cyp3a4_strong_inhibitor")
    if not cyp_inh:
        return None

    # 辛伐他汀风险最高
    is_simva = any("辛伐" in s or "simva" in s for s in statin)
    severity = Severity.HIGH if is_simva else Severity.MEDIUM

    return Alert(
        rule_id="ddi.statin_cyp3a4",
        category="ddi",
        severity=severity,
        title="他汀与 CYP3A4 强抑制剂合用",
        message=(
            f"你在服用他汀（{', '.join(set(statin))}）和 CYP3A4 强抑制剂"
            f"（{', '.join(set(cyp_inh))}）。强抑制会使他汀血药浓度显著升高，"
            "肌病和横纹肌溶解风险上升，尤其是辛伐他汀。"
        ),
        action=(
            "联系处方医生评估是否换用瑞舒伐他汀/普伐他汀（非 CYP3A4 代谢）；"
            "出现肌肉酸痛、无力、尿色加深请立即停药并就医。"
        ),
        data_citation={"statin": statin, "cyp3a4_inhibitor": cyp_inh},
        requires_medical_attention=True,
    )


# ─────────────────────── SSRI × MAOI ─────────────


@register
def ddi_ssri_maoi_serotonin(twin: HealthTwin) -> Optional[Alert]:
    """SSRI + MAOI → 5-羟色胺综合征。绝对禁忌。"""
    meds = _med_names(twin)
    ssri = _has_drug_class(meds, "ssri")
    maoi = _has_drug_class(meds, "mao_inhibitor")
    if not ssri or not maoi:
        return None

    # 氟西汀半衰期长（活性代谢物去甲氟西汀），FDA 标签要求停用后 ≥5 周方可起始 MAOI，
    # 远超其它 SSRI 的 ≥2 周。匹配到氟西汀时洗脱期措辞必须按 5 周给，否则临床上是错的。
    has_fluoxetine = any(
        ("氟西汀" in s) or ("fluoxetine" in s.lower()) for s in ssri
    )
    if has_fluoxetine:
        washout = (
            "洗脱期是有方向性的：停 MAOI → 间隔 ≥14 天再起始 SSRI；"
            "停氟西汀 → 因半衰期长、活性代谢物去甲氟西汀蓄积，需间隔 ≥5 周（约 5 weeks）"
            "再起始 MAOI（其它 SSRI 为 ≥2 周）。"
        )
    else:
        washout = (
            "洗脱期是有方向性的：停 MAOI → 间隔 ≥14 天再起始 SSRI；"
            "停 SSRI → 间隔 ≥2 周再起始 MAOI。"
        )

    return Alert(
        rule_id="ddi.ssri_maoi",
        category="ddi",
        severity=Severity.CRITICAL,
        title="SSRI 与 MAOI 合用 —— 绝对禁忌",
        message=(
            f"SSRI ({', '.join(set(ssri))}) 与 MAOI ({', '.join(set(maoi))}) 合用会引发致命的"
            "5-羟色胺综合征（高热、肌阵挛、抽搐、循环衰竭）。" + washout
        ),
        action="立即联系处方医生停用其中一种；如果已经出现高热/震颤/意识改变立即急诊。",
        data_citation={"ssri": ssri, "maoi": maoi},
        requires_medical_attention=True,
    )


# ─────────────────────── ACE/ARB × 高钾 NSAID ─────────


@register
def ddi_aceiarb_nsaid_kidney(twin: HealthTwin) -> Optional[Alert]:
    """ACEI/ARB + NSAID → 急性肾损伤 + 高钾血症风险。"""
    meds = _med_names(twin)
    acei = _has_drug_class(meds, "acei_arb")
    nsaid = _has_drug_class(meds, "nsaid")
    if not acei or not nsaid:
        return None

    return Alert(
        rule_id="ddi.aceiarb_nsaid",
        category="ddi",
        severity=Severity.MEDIUM,
        title="ACEI/ARB 与 NSAID 合用",
        message=(
            f"{', '.join(set(acei))} 与 {', '.join(set(nsaid))} 合用会收缩肾入球动脉，"
            "在脱水或已有肾功能减退时容易诱发急性肾损伤和高钾血症。"
        ),
        action=(
            "能避免就尽量避免合用；疼痛首选对乙酰氨基酚；"
            "确有必要合用时保证充分饮水，定期复查肾功能和电解质。"
        ),
        data_citation={"acei_arb": acei, "nsaid": nsaid},
    )
