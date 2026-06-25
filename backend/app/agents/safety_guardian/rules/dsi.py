"""
药物-补剂相互作用规则 (DSI)。

针对用户补剂库里常见条目 + 在服药物的组合。
大多数是"时机错开"级别的提醒（吸收拮抗），少数是真正的风险（鱼油+抗凝）。
"""

import re
from datetime import date
from typing import List, Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.rules.ddi import _has_drug_class, _med_names
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin
from app.utils.timezone import get_china_today


# ─────────────────────── 补剂名关键字库 ─────────────────

SUPP_ALIASES = {
    "calcium": ["calcium", "钙", "碳酸钙", "柠檬酸钙"],
    "iron": ["iron", "铁", "血红素铁", "硫酸亚铁", "甘氨酸亚铁"],
    "zinc": ["zinc", "锌", "甘氨酸锌"],
    "magnesium": ["magnesium", "镁", "甘氨酸镁", "苏糖酸镁"],
    "omega3": ["omega", "鱼油", "fish oil", "epa", "dha"],
    "vitamin_k": ["vitamin k", "维生素 k", "vitamin-k", "vk"],
    "st_johns_wort": ["st john", "贯叶连翘", "圣约翰草"],
    "grapefruit": ["grapefruit", "葡萄柚", "西柚"],
    "ginkgo": ["ginkgo", "银杏"],
    "garlic": ["garlic", "大蒜"],
    "curcumin": ["curcumin", "姜黄素", "turmeric"],
    "coq10": ["coq10", "co-q10", "辅酶 q10", "辅酶q10", "ubiquinol"],
    "vitamin_d": ["vitamin d", "维生素 d", "vitamin-d"],
    "b12": ["b12", "甲钴胺", "cyanocobalamin", "methylcobalamin"],
    "folate": ["folate", "叶酸", "methyl folate", "甲基叶酸"],
    "niacin": ["niacin", "烟酸", "nicotinic"],
    "probiotic": ["probiotic", "益生菌", "lactobif", "akk", "akkermansia", "lactobacillus"],
}


def _supplement_names(twin: HealthTwin) -> List[str]:
    return [
        (s.get("name") or "").strip().lower()
        for s in (twin.supplement.active_supplements or [])
        if s.get("name")
    ]


def _has_supplement(names: List[str], class_key: str) -> List[str]:
    aliases = SUPP_ALIASES.get(class_key, [])
    matched: List[str] = []
    for name in names:
        for alias in aliases:
            if alias.lower() in name:
                matched.append(name)
                break
    return matched


# ─────────────────────── GLP-1 × 口服补剂 ─────────────────


@register
def dsi_glp1_oral_supplement_timing(twin: HealthTwin) -> Optional[Alert]:
    """GLP-1 延迟胃排空，会影响口服补剂吸收（尤其需要酸性胃环境的 B12/铁）。"""
    meds = _med_names(twin)
    glp1 = _has_drug_class(meds, "glp1")
    if not glp1:
        return None

    supps = _supplement_names(twin)
    sensitive = []
    sensitive += _has_supplement(supps, "b12")
    sensitive += _has_supplement(supps, "iron")
    sensitive += _has_supplement(supps, "calcium")
    if not sensitive:
        return None

    return Alert(
        rule_id="dsi.glp1_oral_absorption",
        category="dsi",
        severity=Severity.LOW,
        title="GLP-1 对口服补剂吸收的影响",
        message=(
            f"你在使用 GLP-1（{', '.join(set(glp1))}）且有对吸收敏感的补剂"
            f"（B12/铁/钙：{', '.join(sensitive[:4])}{'...' if len(sensitive) > 4 else ''}）。"
            "延迟胃排空可能略降低这些补剂的吸收效率，但影响通常较轻。"
        ),
        action=(
            "敏感补剂建议在早餐前空腹服用（此时胃 pH 最适合 B12/铁吸收）；"
            "铁和钙不要同时服用（互相竞争吸收）。"
        ),
        data_citation={"glp1": glp1, "sensitive_supplements": sensitive},
    )


# ─────────────────────── Omega-3 × 抗凝/抗血小板 ─────────


@register
def dsi_omega3_anticoagulant(twin: HealthTwin) -> Optional[Alert]:
    """高剂量鱼油 + 抗凝/抗血小板 → 轻度出血风险增加。"""
    supps = _supplement_names(twin)
    omega = _has_supplement(supps, "omega3")
    if not omega:
        return None

    meds = _med_names(twin)
    warf = _has_drug_class(meds, "warfarin")
    antip = _has_drug_class(meds, "antiplatelet")
    nsaid = _has_drug_class(meds, "nsaid")
    concomitant = warf + antip + nsaid
    if not concomitant:
        return None

    return Alert(
        rule_id="dsi.omega3_bleeding",
        category="dsi",
        severity=Severity.MEDIUM if warf else Severity.LOW,
        title="鱼油与抗凝/抗血小板药物合用",
        message=(
            f"你在服用 Omega-3（{', '.join(set(omega))}）同时有抗凝/抗血小板/NSAID"
            f"（{', '.join(set(concomitant))}）。高剂量鱼油（>3g/日 EPA+DHA）有轻度抑制血小板聚集作用，"
            "理论上会叠加出血风险。"
        ),
        action=(
            "日常剂量（≤2g/日 EPA+DHA）通常安全；"
            "术前一般无需常规停用鱼油（2018 多国 RCT n=1516 与 2020 SPAQI 共识：鱼油不增加围手术期出血，"
            "鱼油组输血量反而更低），是否暂停由手术团队最终决定；"
            "华法林使用者定期监测 INR；出现皮下瘀斑、牙龈出血、黑便及时就医。"
        ),
        data_citation={"omega3": omega, "concomitant": concomitant},
    )


# ─────────────────────── 钙/铁 吸收拮抗 ─────────────────


@register
def dsi_calcium_iron_competition(twin: HealthTwin) -> Optional[Alert]:
    """钙和铁同时服用会互相竞争吸收 —— 时机错开建议。"""
    supps = _supplement_names(twin)
    cal = _has_supplement(supps, "calcium")
    fe = _has_supplement(supps, "iron")
    if not (cal and fe):
        return None

    return Alert(
        rule_id="dsi.calcium_iron_competition",
        category="dsi",
        severity=Severity.INFO,
        title="钙与铁建议错开服用",
        message=(
            f"你同时在服用钙（{', '.join(cal[:2])}）和铁（{', '.join(fe[:2])}）补剂。"
            "钙会竞争铁的吸收位点，使吸收效率下降约 50%。"
        ),
        action="两者间隔至少 2 小时（例如钙随晚餐、铁早餐前空腹）；富含维 C 的水果/蔬菜可以增强铁吸收。",
        data_citation={"calcium": cal, "iron": fe},
    )


# ─────────────────────── Vitamin K × 华法林 ─────────


@register
def dsi_vitamink_warfarin(twin: HealthTwin) -> Optional[Alert]:
    """维生素 K 补充会显著降低华法林效力。"""
    meds = _med_names(twin)
    warf = _has_drug_class(meds, "warfarin")
    if not warf:
        return None

    supps = _supplement_names(twin)
    vk = _has_supplement(supps, "vitamin_k")
    if not vk:
        return None

    return Alert(
        rule_id="dsi.vitamink_warfarin",
        category="dsi",
        severity=Severity.HIGH,
        title="维生素 K 与华法林相互拮抗",
        message=(
            f"你同时有华法林（{', '.join(warf)}）和维生素 K 补剂（{', '.join(vk)}）。"
            "维 K 是华法林直接拮抗剂，合用会使 INR 下降、抗凝不足。"
        ),
        action=(
            "与处方医生和药师确认是否需要停用维 K 补剂；"
            "若确需合用必须保持维 K 每日摄入稳定（不能今天吃 200 μg 明天吃 0）；"
            "勤查 INR。"
        ),
        data_citation={"warfarin": warf, "vitamin_k_supp": vk},
        requires_medical_attention=True,
    )


# ─────────────────────── 圣约翰草 × 多数药物 ─────────


@register
def dsi_st_johns_wort_multiple(twin: HealthTwin) -> Optional[Alert]:
    """
    St. John's Wort 诱导 CYP3A4 和 P-gp，显著降低多数药物血药浓度：
    避孕药、华法林、免疫抑制剂、SSRI（致 5-羟色胺综合征）等。
    """
    supps = _supplement_names(twin)
    sjw = _has_supplement(supps, "st_johns_wort")
    if not sjw:
        return None

    meds = _med_names(twin)
    if not meds:
        return None

    return Alert(
        rule_id="dsi.st_johns_wort",
        category="dsi",
        severity=Severity.HIGH,
        title="圣约翰草与药物合用风险",
        message=(
            f"你在服用圣约翰草/贯叶连翘（{', '.join(sjw)}）。这是强 CYP3A4 诱导剂，"
            "会降低大多数处方药物血药浓度，包括避孕药、华法林、免疫抑制剂、抗 HIV 药、"
            "他汀、某些抗凝；同时与 SSRI 合用会引发 5-羟色胺综合征。"
        ),
        action="强烈建议停用圣约翰草，或与每个处方药的药师逐一确认合用是否安全。",
        data_citation={"st_johns_wort": sjw, "active_meds": meds},
        requires_medical_attention=True,
    )


# ─────────────────────── 葡萄柚 × CYP3A4 底物 ─────────


@register
def dsi_grapefruit_cyp3a4(twin: HealthTwin) -> Optional[Alert]:
    """葡萄柚汁抑制肠壁 CYP3A4，使多种药物浓度升高。"""
    supps = _supplement_names(twin)
    gf = _has_supplement(supps, "grapefruit")
    if not gf:
        return None

    meds = _med_names(twin)
    statins = _has_drug_class(meds, "statin")
    if not statins:
        return None

    return Alert(
        rule_id="dsi.grapefruit_statin",
        category="dsi",
        severity=Severity.MEDIUM,
        title="葡萄柚与他汀合用",
        message=(
            "葡萄柚汁抑制肠壁 CYP3A4，使辛伐他汀/阿托伐他汀血药浓度显著升高，"
            "肌病和横纹肌溶解风险增加。"
        ),
        action="服用他汀期间避免饮用葡萄柚汁和食用葡萄柚；若经常饮用请换用瑞舒伐他汀或普伐他汀（不受 CYP3A4 影响）。",
        data_citation={"grapefruit": gf, "statin": statins},
    )


# ─────────────────────── 大蒜/姜黄/银杏 × 抗凝 ─────────


@register
def dsi_herbal_bleeding_stack(twin: HealthTwin) -> Optional[Alert]:
    """大蒜/姜黄/银杏 + 抗凝 → 出血风险叠加。"""
    supps = _supplement_names(twin)
    herbs = (
        _has_supplement(supps, "garlic")
        + _has_supplement(supps, "curcumin")
        + _has_supplement(supps, "ginkgo")
    )
    if not herbs:
        return None

    meds = _med_names(twin)
    bleeding_meds = (
        _has_drug_class(meds, "warfarin")
        + _has_drug_class(meds, "antiplatelet")
    )
    if not bleeding_meds:
        return None

    return Alert(
        rule_id="dsi.herbs_bleeding_stack",
        category="dsi",
        severity=Severity.MEDIUM,
        title="草药补剂叠加出血风险",
        message=(
            f"你在同时服用抗凝/抗血小板药（{', '.join(set(bleeding_meds))}）和"
            f"草药补剂（{', '.join(set(herbs))}）。大蒜、姜黄、银杏都有抑制血小板聚集作用，"
            "叠加后出血风险可察觉地增加。"
        ),
        action="术前 1-2 周停用这些草药；观察皮下瘀斑和牙龈出血。",
        data_citation={"bleeding_meds": bleeding_meds, "herbs": herbs},
    )


# ─────────── 长期抑酸(PPI/P-CAB)× 营养缺乏 化验感知 ───────────

# 营养素 → (匹配关键词, 排除词)。排除词防分析物混淆:转铁蛋白≠铁蛋白、尿镁≠血清镁。
# 只匹配 item_name(避免单位 "mg" 误配);血清铁是不稳定标志物,故只认铁蛋白。
_ACID_SUPPRESSION_NUTRIENTS = {
    "维生素B12": (["维生素b12", "维生素 b12", "维生素b-12", "b12", "b-12", "钴胺", "cobalamin"], []),
    "镁": (["血清镁", "血镁", "镁离子", "镁", "magnesium"], ["尿"]),
    "铁蛋白": (["铁蛋白", "ferritin"], ["转铁"]),
}

# P-CAB(钾离子竞争性酸阻滞剂,如伏诺拉生)—— 抑酸机制与 PPI 相近,但长期营养数据更少,加 caveat。
_PCAB_KEYWORDS = ["伏诺拉生", "沃克", "vonoprazan", "p-cab", "pcab"]


def _ppi_keywords() -> List[str]:
    """单一真相源:复用 deprescribing_review 的抑酸药名单(懒导入，避免规则装载期耦合)。"""
    try:
        from app.services.deprescribing_review import _CLASS_KEYWORDS

        return list(_CLASS_KEYWORDS.get("抑酸药(PPI/P-CAB)", []))
    except Exception:  # pragma: no cover - 退化到内置名单，fail-loud 不静默丢规则
        return ["泮托拉唑", "奥美拉唑", "埃索美拉唑", "雷贝拉唑", "兰索拉唑", "伏诺拉生"]


def _is_below_range(value, reference_range) -> Optional[bool]:
    """value < 参考下限 → True;> 下限/无法判向 → False;不可解析或缺值 → None。"""
    if value is None or not reference_range:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    rr = str(reference_range)
    # lo-hi:兼容多种分隔符(ASCII - ~、全角 ～－、中文 至、en/em dash);收紧数字 token 防误锚
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~～–—－至]\s*(\d+(?:\.\d+)?)", rr)
    if m:
        return v < float(m.group(1))
    # 仅下限:≥X / >X / >=X
    m2 = re.search(r"[≥>＞]\s*=?\s*(\d+(?:\.\d+)?)", rr)
    if m2:
        return v < float(m2.group(1))
    return None  # 不可解析(如 "<X"、纯文字) → 交 unclear 分支兜底,不静默当正常


@register
def long_term_acid_suppression_lab_aware(twin: HealthTwin) -> Optional[Alert]:
    """长期抑酸(PPI/P-CAB)× B12/镁/铁吸收。化验感知、确定性、**非处方**。

    长期抑制胃酸与 B12/镁/铁吸收下降相关(FDA 2011 镁警示;B12 吸收依赖胃酸)。
    本规则把胃溃疡愈合模板里"长期 PPI 评估 B12/镁"这句死文字变成活规则:
    - 长期抑酸 且 近期化验示相关营养素**确证偏低** → MEDIUM,建议带给处方医生复评/监测;
    - 长期抑酸 但无近期化验 → INFO,建议下次复诊加查 B12/镁。
    R4:只说"讨论/复评/监测/查",绝不出"停药/减量/剂量"。决策永远在医生。
    """
    ppi_kw = _ppi_keywords()
    ppi_meds = [
        m for m in (twin.medication.active_meds or [])
        if any(kw in (m.get("name") or "") for kw in ppi_kw)
    ]
    if not ppi_meds:
        return None

    # 时长:仅用 start_date 算(京历);任一 PPI 缺 start_date 不臆测,取有日期者的最长时长。
    today = get_china_today()
    weeks = []
    for m in ppi_meds:
        sd = m.get("start_date")
        d: Optional[date] = None
        if isinstance(sd, date):
            d = sd
        elif isinstance(sd, str) and sd:
            try:
                d = date.fromisoformat(sd[:10])
            except ValueError:
                d = None
        if d is not None:
            weeks.append((today - d).days / 7.0)
    if not weeks:
        return None  # 无 start_date → 无法判时长 → 不臆测(fail-closed 对 advisory 是安全方向)
    weeks_on = max(weeks)
    if weeks_on < 8:  # = deprescribing LONG_TERM_WEEKS
        return None
    weeks_int = int(weeks_on)
    ppi_names = sorted({m.get("name") for m in ppi_meds if m.get("name")})

    # 营养素分类:low=确证偏低;unclear=被标记异常但方向不可解析。**两者都不能静默丢**——
    # 不可解析的 flagged-abnormal 营养素进 unclear 兜底,避免漏掉真低值(under-alarm,审评 BLOCKING)。
    low_nutrients: List[str] = []
    unclear_nutrients: List[str] = []
    for item in (twin.labs.flagged_abnormal or []):
        iname = (item.get("item_name") or "").lower()
        for label, (kws, excludes) in _ACID_SUPPRESSION_NUTRIENTS.items():
            if any(kw in iname for kw in kws) and not any(ex in iname for ex in excludes):
                below = _is_below_range(item.get("value"), item.get("reference_range"))
                if below is True:
                    low_nutrients.append(label)
                elif below is None:  # flagged abnormal 但方向不可解析 → 不当正常
                    unclear_nutrients.append(label)
                # below is False(确证不低,如偏高)→ 忽略
                break
    low_nutrients = sorted(set(low_nutrients))
    unclear_nutrients = sorted(set(unclear_nutrients) - set(low_nutrients))

    has_pcab = any(
        any(k in (m.get("name") or "").lower() for k in _PCAB_KEYWORDS) for m in ppi_meds
    )
    pcab_note = (
        "（注:你在用的是 P-CAB 类强效抑酸药,抑酸机制与 PPI 相近,但长期营养影响的研究数据更少,"
        "更值得复诊时一并评估。）"
        if has_pcab
        else ""
    )

    if low_nutrients or unclear_nutrients:
        if low_nutrients:
            finding = f"近期化验提示 {'、'.join(low_nutrients)} 偏低"
            title = "长期抑酸 + 营养指标偏低"
        else:
            finding = f"近期化验把 {'、'.join(unclear_nutrients)} 标记为异常(具体方向需医生结合报告核读)"
            title = "长期抑酸 + 营养指标异常"
        return Alert(
            rule_id="dsi.long_term_acid_suppression_lab",
            category="dsi",
            severity=Severity.MEDIUM,
            title=title,
            message=(
                f"你在用抑酸药（{', '.join(ppi_names)}）已约 {weeks_int} 周（≥8 周），"
                f"且{finding}。长期抑制胃酸会降低维生素 B12、镁、铁的吸收。"
                "**这不是停药建议** —— 请把「长期抑酸 + 上述化验情况」带给开药医生，"
                "由医生判断是否需要复评抑酸方案、定期监测或营养补充。" + pcab_note
            ),
            action="下次复诊把「长期抑酸 + 上述化验情况」告诉处方医生，由医生决定复评/监测/补充。",
            data_citation={
                "ppi_meds": ppi_names,
                "weeks_on": weeks_int,
                "low_nutrients": low_nutrients,
                "flagged_unclear_nutrients": unclear_nutrients,
                "has_pcab": has_pcab,
            },
            references=[
                "https://www.fda.gov/drugs/drug-safety-and-availability/fda-drug-safety-communication-low-magnesium-levels-can-be-associated-long-term-use-proton-pump-inhibitors",
            ],
            requires_medical_attention=True,
        )

    # 长期但无近期化验 → 预防性 INFO(用 last_exam_date 作"近期是否查过"的代理;
    # 无法逐项判"B12 是否查过",故只在确无近期体检/体检过旧时提示，避免对刚查正常者唠叨)
    last_exam = twin.labs.last_exam_date
    stale = (last_exam is None) or ((today - last_exam).days > 180)
    if stale:
        return Alert(
            rule_id="dsi.long_term_acid_suppression_monitor",
            category="dsi",
            severity=Severity.INFO,
            title="长期抑酸 —— 建议查 B12/镁",
            message=(
                f"你在用抑酸药（{', '.join(ppi_names)}）已约 {weeks_int} 周。长期抑制胃酸"
                "与维生素 B12、镁、铁吸收下降相关，而你近期没有相关化验记录。"
                "建议下次复诊或体检时查一下 B12 和镁，便于评估。" + pcab_note
            ),
            action="下次体检/复诊加查血清维生素 B12、镁（必要时铁蛋白）。",
            data_citation={
                "ppi_meds": ppi_names,
                "weeks_on": weeks_int,
                "last_exam_date": last_exam.isoformat() if last_exam else None,
                "has_pcab": has_pcab,
            },
        )
    return None
