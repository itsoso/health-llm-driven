"""
Supplement Advisor —— 基因 + 化验驱动的补剂推荐 specialist.

核心逻辑：
1. 从 Twin 抽取 SNP / lab 异常 / 现用药物
2. 按优先级 pathway 推荐补剂（methylation → cardiovascular → antioxidant → mineral）
3. 硬阻断规则（HFE C282Y 纯合 → 禁铁；孕期 → 禁视黄醇 VitA）
4. 产生 ProposedCard 作为 N-of-1 12 周试验方案（评 Hcy / ApoB / 25-OH-D / HRV）

合规措辞 (R4 红线: 不开方 / 不调量):
- 所有字段带 `disclaimer` 标明"健康参考信息"
- summary 用"建议讨论" / "可考虑"而非"您需要"
- **`dose` 字段不携带"基因型→具体剂量"的开方式数值** —— 一律是去基因门控的
  "可考虑补充 X，剂量遵医嘱 / 已确认方案"。具体数字只出现在 `dose_reference`，且
  明确标注为"指南衍生的一般参考范围，非按你基因型的个体化处方，须医生确认"。
  (对抗验证 2026-06-17: MTHFR→5-MTHF 剂量 / VDR→VD3 剂量被判 prescribes_or_diagnoses
   越界; 主流指南 IOM / Endocrine Society 不推荐基因导向给药。见
   docs/design/health-os/planning-methodology.md §7。)
- 超 UL 剂量自动封顶 + 加 warning 标记 (`_apply_ul_guardrail`，对参考范围上限生效)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.orchestrator.schema import Intent, ProposedCard, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)

DISCLAIMER = "健康参考信息，非医疗诊断。剂量与是否服用建议与医生讨论。"

# ─────────────────────── 复测窗 = 指标生物响应动力学 ───────────────────────
# planning-methodology.md §原则 2/3: 复测窗须按所选指标的响应动力学分别设定，
# 不能对所有补剂统一 84 天 —— 测得太早会把"还没起效"误读成"无效"。
# 取每种指标响应区间偏保守(偏长)的一端，确保到期时生物效应已充分显现。
#   hcy        同型半胱氨酸 4-8 周   → 56 天
#   ldl        血脂/ApoB   4-12 周   → 84 天
#   vitamin_d  25(OH)D     8-12 周   → 84 天
#   b12        钴胺素      ~数周      → 56 天
#   ferritin   铁蛋白      数月       → 120 天
#   custom     未知指标    保守默认    → 84 天
METRIC_VERIFICATION_DAYS: Dict[str, int] = {
    "hcy": 56,
    "ldl": 84,
    "vitamin_d": 84,
    "b12": 56,
    "ferritin": 120,
    "custom": 84,
}
DEFAULT_VERIFICATION_DAYS = 84

# ─────────────────────────── SNP → 补剂映射 ───────────────────────────
# 每条规则 schema:
#   gene / pathway / supplement / dose / dose_reference / ref_upper / ul_key /
#   timing / reason / monitor_labs / priority / contraindications
# priority 越低越先展示，但 "safety critical" 优先级可盖过。
#
# R4 红线 (不开方 / 不调量):
#   `dose`          —— 去基因门控的非处方指引 ("可考虑补充 X，剂量遵医嘱 / 已确认方案")，
#                      **绝不**携带"基因型→具体剂量"的数值。这是展示给用户的字段。
#   `dose_reference`—— 指南衍生的一般参考范围 (带显式"非按你基因型的个体化处方，须医生确认"
#                      标注)，仅作上下文，不作处方。
#   `ref_upper`/`ul_key` —— 参考范围上限数值 + UL_LIMITS 键，喂 `_apply_ul_guardrail`
#                      做安全上限封顶 (超 UL → 警告 + 封顶)。

SUPPLEMENT_RULES: List[Dict[str, Any]] = [
    # ── Methylation pathway (MTHFR) ──
    {
        "id": "mthfr_methylfolate",
        "gene": "MTHFR",
        "pathway": "methylation",
        "supplement": "5-MTHF (活性叶酸)",
        # 去基因门控: 不由基因型驱动具体剂量 (对抗验证判越界, 见 §7)
        "dose": "可考虑补充活性 5-MTHF；具体剂量遵医嘱 / 已确认方案，不由基因型单独驱动。",
        "dose_reference": (
            "指南衍生的一般参考范围 400–800 µg/日（非按你基因型的个体化处方，须医生确认）；"
            "5-MTHF / 叶酸合计 ≤ 安全上限 UL 1000 µg/日。"
        ),
        "ref_upper": 800,
        "ul_key": "5-MTHF",
        "timing": "早餐后 (循证默认，可与医生确认)",
        "reason": "MTHFR C677T 携带者合成叶酸转化效率可能降低，活性 5-MTHF 绕过该代谢步骤；是否补充与剂量由医生按 Hcy / 叶酸基线决定。",
        "monitor_labs": ["同型半胱氨酸 (Hcy)", "血清叶酸"],
        "brands_intl": ["Thorne 5-MTHF 1mg", "Pure Encapsulations Folate 400"],
        "brands_cn": ["活性叶酸 Metafolin"],
        "priority": 10,
        "contraindications": ["未诊断的维生素 B12 缺乏（单补叶酸可能掩盖巨幼贫血）"],
    },
    {
        "id": "mthfr_b12",
        "gene": "MTHFR",
        "pathway": "methylation",
        "supplement": "甲钴胺 (Methylcobalamin)",
        "dose": "可考虑补充甲钴胺；具体剂量遵医嘱 / 已确认方案。",
        "dose_reference": (
            "指南衍生的一般参考范围 500–1000 µg/日（非按基因型的个体化处方，须医生确认）。"
        ),
        "ref_upper": 1000,
        "ul_key": "甲钴胺",
        "timing": "早餐后 (循证默认)",
        "reason": "甲基化周期需要 B12 协同，甲钴胺是活性形式；是否补充与剂量由医生按 B12 / MMA 基线决定。",
        "monitor_labs": ["血清 B12", "MMA (甲基丙二酸)"],
        "priority": 11,
    },
    # ── APOE ε4 ──
    {
        "id": "apoe_omega3",
        "gene": "APOE",
        "pathway": "cardiovascular",
        "supplement": "Omega-3 (EPA+DHA)",
        "dose": "可考虑补充 Omega-3；具体剂量遵医嘱 / 已确认方案。",
        "dose_reference": (
            "指南衍生的一般参考范围 EPA+DHA 合计 1–2 g/日（须医生确认；抗凝者需监测出血风险）。"
        ),
        "ref_upper": 2000,
        "ul_key": "Omega-3",
        "timing": "随正餐 (含脂肪)",
        "reason": "APOE ε4 携带者心血管 / AD 风险升高，Omega-3 与降 ApoB/TG、抗炎相关；是否补充与剂量由医生决定。",
        "monitor_labs": ["ApoB", "LDL-C", "甘油三酯"],
        "brands_intl": ["Nordic Naturals Ultimate Omega"],
        "brands_cn": ["星鲨鱼油"],
        "priority": 20,
        "contraindications": ["抗凝药物 (华法林/阿司匹林) — 高剂量可能增加出血，需医生监测"],
    },
    # ── FADS1/2 ──
    {
        "id": "fads_epa",
        "gene": "FADS1",
        "pathway": "fatty_acid",
        "supplement": "高 EPA 鱼油 (直接 EPA/DHA)",
        "dose": "可考虑补充直接 EPA/DHA；具体剂量遵医嘱 / 已确认方案。",
        "dose_reference": (
            "指南衍生的一般参考范围 EPA ≥ 500 mg/日（须医生确认）。"
        ),
        "ref_upper": 500,
        "ul_key": "Omega-3",
        "timing": "随正餐",
        "reason": "FADS1/2 慢型 ALA→EPA 转化率较低，纯植物来源可能不足，直接补 EPA/DHA 更直接；剂量由医生决定。",
        "monitor_labs": ["Omega-3 index (>8%)", "甘油三酯"],
        "priority": 21,
    },
    # ── 镁 (主观睡眠/焦虑 或 低镁化验触发, 非基因门控) ──
    # 旧版按 COMT 慢型基因型推荐 (id=comt_magnesium), 已纠正:COMT 单 SNP 对认知/焦虑
    # 解释方差<1%、候选基因时代未复现 (见 gene_config.py:224 + 基因解读 first-principles
    # 文档 Tier DE-EMPHASIZE), 且无 COMT×镁→HRV/睡眠 的基因-环境交互证据。镁的
    # 副交感/睡眠效应是未选基因人群 RCT 支持的群体主效应 → 不再归因于任何基因型。
    {
        "id": "magnesium_sleep",
        # gene 故意留空: 镁是群体主效应, 不归因于基因型 (_rule_to_rec → gene=None)
        "pathway": "sleep_recovery",
        "supplement": "甘氨酸镁 (Mg-Glycinate)",
        "dose": "可考虑补充甘氨酸镁；具体剂量遵医嘱 / 已确认方案。",
        "dose_reference": (
            "指南衍生的一般参考范围 200–400 mg 元素镁/日（须医生确认；肾功能不全需减量）。"
        ),
        "ref_upper": 400,
        "ul_key": "甘氨酸镁",
        "timing": "睡前",
        "reason": (
            "镁参与 GABA 能信号与副交感神经张力调节,对主观睡眠质量与焦虑有一定帮助"
            "(未选基因人群 RCT 支持的群体主效应,非基因驱动结论)。"
            "HRV 夜间均值 / PSQI 仅作为 N-of-1 验证终点,不作为基因驱动的预设。"
        ),
        "monitor_labs": ["主观 PSQI", "HRV 夜间均值"],
        "brands_intl": ["Pure Encapsulations Magnesium Glycinate"],
        "brands_cn": ["甘氨酸镁 (汤臣倍健/Swisse)"],
        "priority": 30,
        "contraindications": ["eGFR < 30 (肾功能不全禁高剂量镁)"],
    },
    # ── VDR FokI + 低 25-OH-D ──
    # 主流指南 (IOM / Endocrine Society) 不推荐基因导向的维生素 D 给药 ——
    # 是否补充 / 剂量 / 目标浓度由医生按 25-OH-D 基线 / 肾功能 / 结石史确定, 不由基因型驱动。
    {
        "id": "vdr_vitamin_d",
        "gene": "VDR",
        "pathway": "bone_immune",
        "supplement": "维生素 D3",
        "dose": (
            "维生素 D 是否补充、剂量与目标浓度由医生按 25-OH-D 基线 / 肾功能 / 结石史确定，"
            "不由基因型单独驱动。"
        ),
        "dose_reference": (
            "成人安全上限 UL 4000 IU/日（IOM）；主流指南（IOM / Endocrine Society）"
            "不推荐基因导向给药，目标浓度个体化由医生确定。"
        ),
        "ref_upper": 4000,
        "ul_key": "维生素 D3",
        "timing": "随正餐 (脂溶性)",
        "reason": (
            "VDR FokI 多态可能影响维生素 D 受体信号，但主流指南不推荐按基因型导向补充；"
            "是否补充与目标浓度由医生按 25-OH-D 基线决定。"
        ),
        "monitor_labs": ["25-OH-D（目标浓度由医生个体化确定）"],
        "priority": 31,
        "contraindications": [
            "肾结石史或高钙血症 → 须由医生进一步降量并监测血钙",
            "Sarcoidosis / 活动性结核 → 禁补",
        ],
    },
    {
        "id": "vdr_vitamin_k2",
        "gene": "VDR",
        "pathway": "bone",
        "supplement": "维生素 K2 (MK-7)",
        "dose": "可考虑与 D3 协同补充 K2；具体剂量遵医嘱 / 已确认方案。",
        "dose_reference": (
            "指南衍生的一般参考范围 90–180 µg/日（须医生确认；华法林者禁用）。"
        ),
        "ref_upper": 180,
        "ul_key": "维生素 K2",
        "timing": "随含脂肪餐",
        "reason": "与 D3 协同：D3 促吸钙，K2 导钙入骨；单补 D3 不配 K2 有软组织钙化风险。",
        "monitor_labs": [],
        "priority": 32,
        "contraindications": ["华法林 (K 拮抗抗凝药) — 需重点管理的高风险相互作用，须医生监督 INR"],
    },
    # ── SOD2 / GPX1 抗氧化能力降 ──
    {
        "id": "sod2_coq10",
        "gene": "SOD2",
        "pathway": "antioxidant",
        "supplement": "CoQ10 (Ubiquinol)",
        "dose": "可考虑补充 CoQ10；具体剂量遵医嘱 / 已确认方案。",
        "dose_reference": (
            "指南衍生的一般参考范围 100–200 mg/日（须医生确认）。"
        ),
        "ref_upper": 200,
        "ul_key": "CoQ10",
        "timing": "早餐 (脂溶)",
        "reason": "SOD2 T 型线粒体抗氧化能力可能偏弱；服用 statin 者 CoQ10 内源性合成受抑。",
        "monitor_labs": ["HRV 夜间均值"],
        "priority": 40,
    },
    # ── HFE C282Y 纯合 → 硬阻断铁 ──
    # 注: 这是"禁用"安全阻断 (与开方相反)，dose="禁用" 不属 prescribes_or_diagnoses。
    {
        "id": "hfe_iron_BLOCK",
        "gene": "HFE",
        "pathway": "iron_metabolism",
        "supplement": "❌ 任何含铁补剂",
        "dose": "禁用",
        "timing": "—",
        "reason": "HFE C282Y 纯合 (遗传性血色病) → 机体铁吸收失调，补铁会加剧铁过载，引发肝/胰/心损伤。",
        "monitor_labs": ["Ferritin (>300 ng/mL 危险)", "TSAT (>45% 危险)"],
        "priority": 1,  # safety critical, 最高优先级
        "is_block": True,
    },
]


# ─────────────────────────── 实验剂量警告 (UL 上限) ───────────────────

UL_LIMITS = {
    "维生素 D3": 4000,          # IU/day safe upper
    "维生素 D": 4000,
    "Omega-3": 5000,            # mg EPA+DHA, FDA GRAS
    "5-MTHF": 1000,             # µg
    "叶酸": 1000,                # µg
    "甲钴胺": 2000,              # µg, 无严格 UL
    "CoQ10": 1200,              # mg
    "甘氨酸镁": 800,             # mg elemental mg
    "维生素 K2": 300,            # µg
}


def _apply_ul_guardrail(
    ul_key: Optional[str], ref_upper: Optional[float]
) -> Tuple[Optional[float], Optional[str]]:
    """对"参考范围上限"做安全上限 (UL) 封顶。

    这是真护栏 (历史上 UL_LIMITS 是死代码，从未被消费 —— 现接入 `_rule_to_rec`)。
    返回 (封顶后的安全上限值, 警告文案)。
    - ul_key 不在 UL_LIMITS 或 ref_upper 缺失 → (None, None) 不干预。
    - ref_upper 超 UL → 返回 (UL, 警告) ：把展示上限压到 UL，并提示不可超过。
    - ref_upper ≤ UL → 返回 (UL, None) ：仅回传 UL 作为天花板供展示，不警告。
    """
    if not ul_key or ref_upper is None:
        return None, None
    ul = UL_LIMITS.get(ul_key)
    if ul is None:
        return None, None
    if ref_upper > ul:
        return ul, (
            f"⚠️ 参考范围上限 {ref_upper} 超安全上限 UL {ul}（{ul_key}）→ "
            f"已按 UL 封顶，任何情况下不可超过 {ul}，且须遵医嘱。"
        )
    return ul, None


# ─────────────────────────── 辅助函数 ───────────────────────────


def _has_snp(twin: HealthTwin, gene: str, variant_match: Optional[str] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """检查 twin.genetic 里是否有指定基因的风险/营养变异。返回 (命中, 变异记录)."""
    if not twin.genetic.has_profile:
        return False, None

    all_variants = (
        (twin.genetic.nutrition_variants or [])
        + (twin.genetic.risk_variants or [])
        + (twin.genetic.drug_sensitivity or [])
        + (twin.genetic.recovery_variants or [])
    )

    gene_upper = gene.upper()
    for v in all_variants:
        vname = (v.get("gene_name") or "").upper()
        if vname != gene_upper:
            continue
        if variant_match:
            geno = (v.get("genotype") or "").upper()
            if variant_match.upper() not in geno:
                continue
        # 需要是风险型或 reduced 型 (APOE ε4 例外：以 genotype 为准)
        label = (v.get("result_label") or "").lower()
        risk = (v.get("risk_level") or "").lower()
        geno = (v.get("genotype") or "").upper()
        is_risk = (
            "risk" in risk or "高" in risk or "中" in risk
            or "poor" in label or "reduced" in label or "慢" in label
            or "TT" in geno or "CC" in geno
            or (gene_upper == "APOE" and "4" in geno)
            or (gene_upper == "HFE" and ("C282Y" in geno or "C282Y/C282Y" in geno))
        )
        if is_risk:
            return True, v
    return False, None


def _is_hfe_homozygous(twin: HealthTwin) -> bool:
    """HFE C282Y 纯合 (血色病) — 硬阻断铁补剂."""
    hit, v = _has_snp(twin, "HFE")
    if not hit or not v:
        return False
    geno = (v.get("genotype") or "").upper()
    # 纯合: C282Y/C282Y 或 TT; 杂合 C282Y/H63D 也风险高但不完全禁
    return "C282Y/C282Y" in geno or geno in ("TT", "YY")


def _lab_abnormal(twin: HealthTwin, keywords: List[str]) -> List[Dict[str, Any]]:
    """twin.labs.flagged_abnormal 里匹配关键字的异常项."""
    if not twin.labs.flagged_abnormal:
        return []
    out = []
    for a in twin.labs.flagged_abnormal:
        name = (a.get("item_name") or "").lower()
        if any(k.lower() in name for k in keywords):
            out.append(a)
    return out


def _active_meds(twin: HealthTwin) -> List[str]:
    """返回正在服用的药名列表（小写）."""
    return [
        (m.get("name") or "").lower()
        for m in (twin.medication.active_meds or [])
        if m.get("name")
    ]


def _has_med(twin: HealthTwin, keywords: List[str]) -> bool:
    meds = _active_meds(twin)
    return any(any(k.lower() in m for k in keywords) for m in meds)


# 镁推荐的症状触发关键字 (取代旧 COMT 基因门控) — 主观睡眠 / 焦虑主诉
_SLEEP_ANXIETY_KEYWORDS = [
    "失眠", "入睡困难", "睡不着", "睡眠差", "睡眠质量差", "易醒", "多梦", "早醒",
    "焦虑", "紧张不安", "insomnia", "poor sleep", "anxiety", "anxious",
]


def _has_sleep_or_anxiety_complaint(twin: HealthTwin) -> bool:
    """主观睡眠/焦虑主诉 — 镁(GABA能/副交感)的症状触发,非基因型驱动."""
    texts: List[str] = []
    texts += twin.acute.recent_symptoms or []
    texts += twin.acute.symptom_texts_all or []
    texts += twin.mental.recent_journal_themes or []
    blob = " ".join(t for t in texts if t).lower()
    if not blob:
        return False
    return any(k.lower() in blob for k in _SLEEP_ANXIETY_KEYWORDS)


# ─────────────────────────── Specialist ───────────────────────────


class SupplementAdvisorSpecialist:
    name = "supplement_advisor"
    category = "fuel"

    TRIGGER_KEYWORDS = {
        "补剂", "吃什么补", "保健品", "维生素", "omega", "鱼油",
        "叶酸", "mthfr", "coq10", "辅酶", "镁", "钙",
        "维d", "维生素d", "b12", "b族",
        "supplement", "vitamin", "omega-3",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "fuel" in intent.categories or "labs" in intent.categories:
            # fuel/labs 意图下, 如果有基因或异常 lab 则参与
            if twin.genetic.has_profile or twin.labs.flagged_abnormal:
                return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            recommendations: List[Dict[str, Any]] = []
            blocks: List[Dict[str, Any]] = []  # 硬阻断项
            warnings: List[str] = []

            # 1. HFE 硬阻断（最优先）
            if _is_hfe_homozygous(twin):
                blocks.append({
                    "type": "hard_block",
                    "supplement": "任何含铁补剂",
                    "reason": "HFE C282Y 纯合（遗传性血色病） → 铁过载风险，严禁补铁。",
                    "monitor_labs": ["Ferritin", "TSAT"],
                    "disclaimer": DISCLAIMER,
                })
                warnings.append("⛔ 基因检测显示血色病风险，严禁所有含铁补剂与高铁食物长期过量摄入。")

            # 2. MTHFR
            hit_mthfr, _ = _has_snp(twin, "MTHFR")
            if hit_mthfr:
                for rid in ("mthfr_methylfolate", "mthfr_b12"):
                    rule = next(r for r in SUPPLEMENT_RULES if r["id"] == rid)
                    recommendations.append(self._rule_to_rec(rule, twin))

            # 3. APOE ε4
            hit_apoe, _ = _has_snp(twin, "APOE")
            if hit_apoe:
                rule = next(r for r in SUPPLEMENT_RULES if r["id"] == "apoe_omega3")
                recommendations.append(self._rule_to_rec(rule, twin))

            # 4. FADS1 (Omega-3 conversion low)
            hit_fads, _ = _has_snp(twin, "FADS1")
            if hit_fads and not hit_apoe:  # APOE 已覆盖 Omega-3
                rule = next(r for r in SUPPLEMENT_RULES if r["id"] == "fads_epa")
                recommendations.append(self._rule_to_rec(rule, twin))

            # 5. 镁 — 症状/化验触发 (非基因门控)
            #    旧版按 COMT 慢型基因型推荐, 已纠正 (无 COMT×镁→HRV/睡眠 交互证据);
            #    改由低镁化验或主观睡眠/焦虑主诉触发, 镁的副交感效应是群体主效应。
            low_mg = _lab_abnormal(twin, ["镁", "magnesium"])
            if low_mg or _has_sleep_or_anxiety_complaint(twin):
                rule = next(r for r in SUPPLEMENT_RULES if r["id"] == "magnesium_sleep")
                rec = self._rule_to_rec(rule, twin)
                # eGFR < 30 禁高剂量镁
                if twin.labs.egfr is not None and twin.labs.egfr < 30:
                    rec["warning"] = "⚠️ eGFR < 30, 镁不宜高剂量 — 建议 100 mg 起步并咨询肾内科。"
                recommendations.append(rec)

            # 6. VDR + 25-OH-D 偏低
            hit_vdr, _ = _has_snp(twin, "VDR")
            low_vd = _lab_abnormal(twin, ["25-OH-D", "25羟", "维生素 D", "维生素D"])
            if hit_vdr or low_vd:
                rule_d = next(r for r in SUPPLEMENT_RULES if r["id"] == "vdr_vitamin_d")
                rec_d = self._rule_to_rec(rule_d, twin)
                # 肾结石史 → 自动降 dose 到 1000 IU + warning (memory 提的硬规则)
                conditions = (twin.chronic.active_conditions or [])
                has_kidney_stone = any(
                    any(k in (cond or "") for k in ["肾结石", "结石", "kidney stone", "nephrolithiasis"])
                    for cond in conditions
                )
                if has_kidney_stone:
                    # 不写具体处方剂量 (R4): 仅做"须由医生进一步降量"的安全提示
                    rec_d["warning"] = (
                        "⚠️ 你有肾结石病史, 高剂量维生素 D 增加钙沉积风险 → "
                        "是否补充及剂量须由医生按血钙 / 25-OH-D 确定（通常更趋保守），不可自行加量。"
                    )
                if _has_med(twin, ["华法林", "warfarin"]):
                    if not has_kidney_stone:
                        rec_d["warning"] = "⚠️ 华法林 × D3 安全, 但 K2 与华法林绝对禁忌 — 本次不建议加 K2."
                    else:
                        rec_d["warning"] = (
                            rec_d.get("warning", "") + " 华法林 × D3 安全, 但 K2 与华法林禁忌 — 不加 K2."
                        )
                    recommendations.append(rec_d)
                else:
                    recommendations.append(rec_d)
                    # 肾结石史也不加 K2 — 钙调控更谨慎
                    if not has_kidney_stone:
                        rule_k = next(r for r in SUPPLEMENT_RULES if r["id"] == "vdr_vitamin_k2")
                        recommendations.append(self._rule_to_rec(rule_k, twin))

            # 7. SOD2 / statin → CoQ10
            hit_sod, _ = _has_snp(twin, "SOD2")
            on_statin = _has_med(twin, ["statin", "他汀", "阿托伐", "瑞舒伐", "辛伐"])
            if hit_sod or on_statin:
                rule = next(r for r in SUPPLEMENT_RULES if r["id"] == "sod2_coq10")
                rec = self._rule_to_rec(rule, twin)
                if on_statin:
                    rec["reason"] += " 用户在服用他汀类药物，CoQ10 合成被抑制。"
                recommendations.append(rec)

            # 8. 总数超 5 个 → 用户易遗忘，降级展示
            if len(recommendations) > 5:
                warnings.append(f"共命中 {len(recommendations)} 项建议，为保证依从性，仅展示优先级最高的 5 项。")
                recommendations.sort(key=lambda r: r.get("priority", 100))
                recommendations = recommendations[:5]

            # ── 构造 findings ──
            findings: List[Dict[str, Any]] = []
            for b in blocks:
                findings.append(b)
            for r in recommendations:
                findings.append({"type": "supplement_rec", **r})
            for w in warnings:
                findings.append({"type": "warning", "message": w})

            # 数据缺口提示
            if not twin.genetic.has_profile and not twin.labs.flagged_abnormal:
                findings.append({
                    "type": "data_gap",
                    "message": "尚无基因检测或体检异常数据，无法做个性化补剂建议。可上传基因报告或体检单。",
                    "disclaimer": DISCLAIMER,
                })

            # ── summary ──
            if blocks:
                summary = f"⛔ {len(blocks)} 条硬阻断 + {len(recommendations)} 条个性化建议"
            elif recommendations:
                summary = f"基于基因/化验找到 {len(recommendations)} 条补剂参考，建议讨论剂量与时机"
            else:
                summary = "暂无明确补剂建议。" + DISCLAIMER

            # ── ProposedCard: N-of-1 12 周试验 (P2 严格化 2026-05-12) ──
            proposed_cards: List[ProposedCard] = []
            if recommendations and not blocks:
                top = recommendations[0]
                monitor_labs = top.get("monitor_labs") or []
                # metric_key 严格映射 monitor_labs → 微营养 fetcher 白名单
                # (hcy/vitamin_d/b12/ferritin/ldl/apob 等都已在 metrics 里实现)
                lab_text = " ".join(monitor_labs).lower()
                if "hcy" in lab_text or "homocy" in lab_text or "同型半胱" in lab_text:
                    metric_key = "hcy"
                elif "ldl" in lab_text:
                    metric_key = "ldl"
                elif "vitamin d" in lab_text or "维生素 d" in lab_text or "25-oh" in lab_text:
                    metric_key = "vitamin_d"
                elif "b12" in lab_text or "钴胺" in lab_text:
                    metric_key = "b12"
                elif "ferritin" in lab_text or "铁蛋白" in lab_text:
                    metric_key = "ferritin"
                elif "apob" in lab_text:
                    metric_key = "ldl"  # apob 暂用 ldl fetcher
                else:
                    metric_key = "custom"

                # 拉用户当前 baseline (如有 — 没的话 verify 会标 inconclusive 而非错评)
                baseline_str: Optional[str] = None
                target_str: str = "改善 ≥ 15%"
                try:
                    from app.tasks.metrics import fetch_metric, HIGHER_IS_BETTER
                    from datetime import date as _date
                    if context and context.get("db") and metric_key != "custom":
                        actual = fetch_metric(
                            context["db"], context.get("user_id") or 0,
                            metric_key, _date.today(),
                        )
                        if actual is not None:
                            baseline_str = f"{actual:.2f}".rstrip("0").rstrip(".")
                            higher_better = HIGHER_IS_BETTER.get(metric_key, False)
                            # 朝目标方向算 ±15% 数值, outcome_grader 能直接 grade
                            target_num = actual * (1.15 if higher_better else 0.85)
                            target_str = f"{target_num:.2f}".rstrip("0").rstrip(".")
                except Exception as e:
                    logger.debug(f"[supplement_advisor] baseline fetch 失败: {e}")

                # 强证据 SNP (CPIC pharmacogenomics 级) 用 high; 其它 medium
                strong_pathways = {"mthfr_methylfolate", "mthfr_b12", "apoe_omega3"}
                top_id = top.get("id") or top.get("rule_id")
                evidence = "high" if top_id in strong_pathways else "medium"

                proposed_cards.append(ProposedCard(
                    title=f"12 周补剂试验：{top['supplement']}",
                    content=(
                        f"## N-of-1 补剂小试验\n\n"
                        f"**补剂**：{top['supplement']}（{top['timing']}）\n"
                        f"**剂量**：{top['dose']}\n"
                        + (f"**剂量参考**：{top['dose_reference']}\n" if top.get("dose_reference") else "")
                        + f"**科学依据**：{top['reason']}\n\n"
                        f"### 验证指标\n"
                        f"- 第 0 / 12 周各查 1 次：{', '.join(monitor_labs) if monitor_labs else '相关指标'}\n"
                        f"- 当前 baseline: {baseline_str or '未测 (建议先做基线化验)'}\n"
                        f"- 目标: {target_str}\n\n"
                        f"### 免责\n{DISCLAIMER}"
                    ),
                    metric_key=metric_key,
                    baseline_value=baseline_str or "0",  # 0 让 verify 标 inconclusive 而非异常
                    target_value=target_str,
                    verification_days=METRIC_VERIFICATION_DAYS.get(
                        metric_key, DEFAULT_VERIFICATION_DAYS
                    ),  # 按指标响应动力学，不再统一 84 天
                    card_type="plan",
                    priority=30,
                    evidence_level=evidence,
                ))

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "rec_count": len(recommendations),
                    "block_count": len(blocks),
                    "gene_profile": twin.genetic.has_profile,
                    "has_lab_abnormal": bool(twin.labs.flagged_abnormal),
                    "disclaimer": DISCLAIMER,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
                proposed_cards=proposed_cards,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[supplement_advisor] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"补剂建议失败: {e}",
                findings=[],
                raw={"error": str(e), "disclaimer": DISCLAIMER},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )

    # ─────────────────────────── 辅助 ───────────────────────────

    def _rule_to_rec(self, rule: Dict[str, Any], twin: HealthTwin) -> Dict[str, Any]:
        """把规则转成给用户的推荐字典，挂免责声明 + 剂量 UL 检查."""
        rec = {
            "id": rule["id"],
            "gene": rule.get("gene"),
            "pathway": rule.get("pathway"),
            "supplement": rule["supplement"],
            # dose 是去基因门控的非处方指引; 具体数字只在 dose_reference (带"须医生确认"标注)
            "dose": rule["dose"],
            "dose_reference": rule.get("dose_reference"),
            "timing": rule["timing"],
            "reason": rule["reason"],
            "monitor_labs": rule.get("monitor_labs", []),
            "brands_intl": rule.get("brands_intl", []),
            "brands_cn": rule.get("brands_cn", []),
            "contraindications": rule.get("contraindications", []),
            "priority": rule.get("priority", 50),
            "disclaimer": DISCLAIMER,
        }
        # UL 安全上限护栏 (对参考范围上限生效, 超 UL → 封顶 + 警告)
        ul_ceiling, ul_warning = _apply_ul_guardrail(rule.get("ul_key"), rule.get("ref_upper"))
        if ul_ceiling is not None:
            rec["ul_ceiling"] = ul_ceiling
        if ul_warning:
            # 不覆盖既有 warning (如肾结石/eGFR), 追加
            rec["warning"] = (rec.get("warning", "") + " " + ul_warning).strip()
        return rec
