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

import re
from typing import List, Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin


# ─────────────────────────── 药名关键字库 ─────────────────────────


# 每个"药物类"下面列出常见中英文别名（小写 + 正则友好）
DRUG_ALIASES = {
    "glp1": [
        "替尔泊肽", "tirzepatide", "司美格鲁肽", "semaglutide", "利拉鲁肽",
        "liraglutide", "杜拉糖肽", "dulaglutide", "艾塞那肽", "exenatide",
        "毕马西肽", "lixisenatide",
    ],
    "insulin": ["胰岛素", "insulin", "优泌林", "甘精", "门冬", "德谷", "赖脯"],
    "sulfonylurea": [
        "格列", "gliclazide", "glimepiride", "glibenclamide", "磺脲",
        "glipizide", "tolbutamide",
    ],
    "cetirizine": ["西替利嗪", "cetirizine", "仙特明", "zyrtec"],
    "first_gen_antihistamine": [
        "苯海拉明", "diphenhydramine", "氯苯那敏", "扑尔敏", "chlorpheniramine",
        "异丙嗪", "promethazine", "羟嗪", "hydroxyzine",
    ],
    "benzodiazepine": [
        "艾司唑仑", "阿普唑仑", "劳拉西泮", "地西泮", "氯硝西泮",
        "diazepam", "alprazolam", "lorazepam", "clonazepam", "estazolam", "midazolam",
    ],
    "opioid": [
        "吗啡", "芬太尼", "可待因", "曲马多", "羟考酮", "布洛芬", "氢可酮",
        "morphine", "fentanyl", "codeine", "tramadol", "oxycodone", "hydrocodone",
    ],
    "warfarin": ["华法林", "warfarin"],
    "antiplatelet": ["氯吡格雷", "clopidogrel", "阿司匹林", "aspirin"],
    "mao_inhibitor": ["苯乙肼", "异丙烟肼", "mao", "phenelzine", "selegiline"],
    "metformin": ["二甲双胍", "metformin", "格华止"],
    "mometasone_nasal": ["糠酸莫米松", "mometasone", "内舒拿", "nasonex"],
    "ipratropium_nasal": ["异丙托溴铵", "ipratropium", "爱全乐", "atrovent"],
    "cyp3a4_strong_inhibitor": [
        "利托那韦", "ritonavir", "克拉霉素", "clarithromycin",
        "酮康唑", "ketoconazole", "伊曲康唑", "itraconazole",
        "泊沙康唑", "posaconazole", "考比司他", "cobicistat",
    ],
    "nsaid": [
        "布洛芬", "ibuprofen", "双氯芬酸", "diclofenac", "萘普生", "naproxen",
        "塞来昔布", "celecoxib", "美洛昔康", "meloxicam",
    ],
    "acei_arb": [
        "普利", "pril", "沙坦", "sartan", "依那普利", "enalapril",
        "缬沙坦", "valsartan", "氯沙坦", "losartan",
    ],
    "ssri": [
        "舍曲林", "sertraline", "氟西汀", "fluoxetine", "帕罗西汀", "paroxetine",
        "西酞普兰", "citalopram", "艾司西酞普兰", "escitalopram",
    ],
    "statin": [
        "他汀", "statin", "辛伐他汀", "simvastatin", "阿托伐他汀", "atorvastatin",
        "瑞舒伐他汀", "rosuvastatin", "普伐他汀", "pravastatin",
    ],
}


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

    return Alert(
        rule_id="ddi.glp1_gastric_emptying",
        category="ddi",
        severity=Severity.LOW,
        title="GLP-1 会延迟胃排空",
        message=(
            f"你在使用 GLP-1 药物（{', '.join(set(glp1))}）。GLP-1 会使胃排空减慢约 30-70 分钟，"
            "对需要快速起效或吸收窗口狭窄的口服药物（例如避孕药、某些抗凝、甲状腺素）可能略有影响。"
        ),
        action="窄治疗窗口的口服药建议在注射日与非注射日之间错开；有避孕需求的女性建议同时使用屏障法；有疑问时咨询药师。",
        data_citation={"glp1_meds": glp1},
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

    return Alert(
        rule_id="ddi.ssri_maoi",
        category="ddi",
        severity=Severity.CRITICAL,
        title="SSRI 与 MAOI 合用 —— 绝对禁忌",
        message=(
            f"SSRI ({', '.join(set(ssri))}) 与 MAOI ({', '.join(set(maoi))}) 合用会引发致命的"
            "5-羟色胺综合征（高热、肌阵挛、抽搐、循环衰竭）。两药停用之间需要 2 周洗脱期。"
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
