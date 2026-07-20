"""
Longevity Specialist —— 解读 PhenoAge(表型年龄)+ 委托四件套给出干预方向。

设计文档:docs/design-longevity-mvp.md §4
上游算子:app/services/phenoage.py(纯函数, Levine 2018)
读取来源:twin.labs.phenotypic_age / delta / claim_boundary
        twin.epigenetic(可选,DNAm 时钟做长期参考)
        twin.body_composition / physiological / behavioral(用于"主要拖累"提示)

诚实纪律(与 EpigeneticState 同款):
- evidence_tier 在 finding 里显式带出
- 不开方、不诊断、不宣称"逆龄/治疗"
- claim_boundary 跟随 finding 输出,展示侧必须呈现
- 干预建议**委托**给 Recovery/Fuel/Movement/Mental,本 specialist 不重复造科学
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, ProposedCard, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


class LongevitySpecialist:
    name = "longevity"
    category = "longevity"

    # 触发关键词(中英,大小写不敏感)
    TRIGGER_KEYWORDS = {
        "抗衰", "抗老", "逆龄", "衰老",
        "生物年龄", "身体年龄", "表型年龄", "phenoage", "phenotypic age",
        "longevity", "aging", "biological age",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        # 1) 显式 intent 命中
        if "longevity" in intent.categories:
            return True
        # 2) 关键字命中
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 3) 当 Twin 已有 PhenoAge 或体能年龄,general 对话也带上一句年龄解读
        if "general" in intent.categories and (
            twin.labs.phenotypic_age is not None
            or twin.physiological.vo2max_fitness_age is not None
        ):
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            L = twin.labs

            if L.phenotypic_age is None:
                # PhenoAge 没算出来 → 但 VO2max 体能年龄(若有)仍是可用的第二信号
                missing = _missing_phenoage_inputs(twin)
                cardio = _cardio_signal(twin, None)
                findings: List[Dict[str, Any]] = [{
                    "type": "phenoage_unavailable",
                    "missing_inputs": missing,
                    "claim_boundary": (
                        "PhenoAge 需要 9 项常规血检 + 实足年龄齐全才能计算,"
                        "缺任一项 → 不猜算,不展示结果。"
                    ),
                }]
                if cardio:
                    findings.append(cardio)
                    fa = cardio.get("fitness_age")
                    summary = (
                        "暂无 PhenoAge(缺血检),但有 VO2max 体能信号"
                        + (f":体能年龄 {fa} 岁" if fa is not None else "")
                        + ";补全血检后可加上表型年龄。"
                    )
                else:
                    summary = (
                        "暂无表型年龄(PhenoAge)结果 — 缺少必要的血检项,"
                        f"补全后即可在体检后自动更新:{', '.join(missing)}"
                    ) if missing else (
                        "暂无表型年龄(PhenoAge)结果 — 缺少近期完整血检报告。"
                    )
                return SpecialistFinding(
                    specialist_name=self.name,
                    category=self.category,
                    summary=summary,
                    findings=findings,
                    raw={"phenoage_status": "unavailable", "missing": missing,
                         "has_cardio": cardio is not None},
                    ms_elapsed=int((time.monotonic() - t0) * 1000),
                    evidence_refs=["levine_2018_phenoage"],
                )

            pa = round(L.phenotypic_age, 1)
            delta = L.phenotypic_age_delta_years
            chrono = round(pa - delta, 1) if delta is not None else None

            drags = _identify_drags(twin)
            findings: List[Dict[str, Any]] = [
                {
                    "type": "phenotypic_age",
                    "phenotypic_age": pa,
                    "chronological_age": chrono,
                    "delta_years": delta,
                    "evidence_tier": L.phenoage_evidence_tier or "validated",
                    "claim_boundary": L.phenoage_claim_boundary or "",
                    "interpretation": _interpret_delta(delta),
                },
            ]

            if drags:
                findings.append({
                    "type": "drags",
                    "items": drags,
                    "note": "下列指标偏离参考区间,可能拉高生物年龄;具体干预由 Recovery/Fuel/Movement/Mental 给出。",
                })

            # DNAm 时钟作为长期参考(若用户做过)
            if twin.epigenetic.has_methylation_report and twin.epigenetic.biological_age is not None:
                findings.append({
                    "type": "epigenetic_cross_ref",
                    "biological_age": twin.epigenetic.biological_age,
                    "delta_years": twin.epigenetic.biological_age_delta_years,
                    "vendor": twin.epigenetic.vendor,
                    "clock_type": twin.epigenetic.clock_type,
                    "evidence_tier": twin.epigenetic.evidence_tier,
                    "claim_boundary": twin.epigenetic.claim_boundary,
                    "note": "甲基化时钟为长期/研究性参考,与 PhenoAge 互补,不直接相互替代。",
                })

            # 第二生物年龄信号:VO2max / 体能年龄(与 PhenoAge 互补,不替代)
            cardio = _cardio_signal(twin, chrono)
            if cardio:
                findings.append(cardio)

            # 真实编排四件套 → 整合 12 周抗衰协议(不再是"委托文字";科学仍由各专家给)
            protocol = _compose_protocol(twin)
            if protocol:
                findings.append({
                    "type": "longevity_protocol",
                    "pillars": protocol,
                    "rationale": "PhenoAge 仅为代理指标;下列 12 周可逆改善路径由四件套专家实时生成。",
                })

            # 数据飞轮:若 context 带 db,取群体已验证证据反哺本次推荐(越多用户越准)
            cohort = _cohort_evidence(context, twin)
            if cohort:
                findings.append({
                    "type": "cohort_evidence",
                    "text": cohort["text"],
                    "n": cohort["n"],
                    "improvement_rate": cohort["improvement_rate"],
                    "mean_improvement_years": cohort["mean_improvement_years"],
                    "evidence_tier": cohort["evidence_tier"],
                })

            summary = _compose_summary(pa, chrono, delta, drags)

            # 偏老(delta ≥ 1)→ 提一张 12 周抗衰 N-of-1 卡:把"单点身体年龄"
            # 变成"干预后变年轻"的可验证闭环。outcome 指标=phenotypic_age(越低越好)。
            proposed_cards = _propose_phenoage_episode(pa, chrono, delta, protocol, cohort)

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                proposed_cards=proposed_cards,
                raw={
                    "phenotypic_age": pa,
                    "delta_years": delta,
                    "inputs_complete": L.phenotypic_age_inputs_complete,
                    "drags_count": len(drags),
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
                evidence_refs=["levine_2018_phenoage", "fitzgerald_2021_lifestyle"],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[longevity] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"抗衰分析失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )


# ─────────────────────────── 内部工具 ───────────────────────────


def _cohort_evidence(context: Dict[str, Any], twin: HealthTwin) -> Optional[Dict[str, Any]]:
    """数据飞轮:从 context.db 取群体已验证证据(无 db / 样本不足 → None,不打扰)。

    飞轮 v2:传 twin.meta.user_id → 优先"和你相似的人"(匹配队列),不足回退人群平均。
    """
    db = (context or {}).get("db")
    if db is None:
        return None
    try:
        from app.services.longevity_cohort_service import cohort_recommendation_snippet

        uid = getattr(twin.meta, "user_id", None) if twin and twin.meta else None
        return cohort_recommendation_snippet(db, "phenotypic_age", similar_to_user_id=uid)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[longevity] cohort evidence 取用失败 (跳过): {e}")
        return None


def _propose_phenoage_episode(
    pa: float, chrono: Optional[float], delta: Optional[float],
    protocol: Optional[List[Dict[str, Any]]] = None,
    cohort: Optional[Dict[str, Any]] = None,
) -> List[ProposedCard]:
    """偏老时提一张 12 周抗衰 N-of-1 卡(outcome=phenotypic_age,越低越好)。

    证据:Fitzgerald 2021 RCT — 8 周生活方式干预 → 生物年龄 −3.23 岁。
    只在 delta ≥ 1(略偏老及以上)提卡;年轻/持平不打扰。
    目标设为下降 ≥2 岁(保守于 RCT 的 −3.23)。不开方、不诊断。
    """
    if delta is None or delta < 1.0:
        return []
    target_pa = round(pa - 2.0, 1)
    chrono_txt = f"实足 {chrono} 岁," if chrono is not None else ""
    # 把编排出的四件套协议写进卡片正文 → 用户拿到的是"具体做什么",不是"去看四件套"
    plan_lines = ""
    if protocol:
        plan_lines = "\n\n**本周期行动(四件套整合):**\n" + "\n".join(
            f"- {p['pillar']}:{p['action']}" for p in protocol
        )
    # 数据飞轮:有群体证据则挂一句(越多用户越有底气;observational 不说因果)
    cohort_line = f"\n\n📊 {cohort['text']}" if cohort and cohort.get("text") else ""
    return [
        ProposedCard(
            title=f"12 周抗衰 N-of-1:身体年龄降到 {target_pa} 岁以下",
            content=(
                f"当前表型年龄 **{pa} 岁**({chrono_txt}偏老 {delta:.1f} 岁)。\n"
                "12 周后复检血检重算 PhenoAge,验证身体年龄是否真的下降"
                "(对照 Fitzgerald 2021:生活方式 8 周可降约 3 岁)。"
                + plan_lines
                + cohort_line
                + "\n\n⚠️ PhenoAge 是血检代理指标,不作诊断、不等于真实衰老速度。"
            ),
            metric_key="phenotypic_age",
            baseline_value=str(pa),
            target_value=f"<{target_pa}",
            verification_days=84,
            card_type="plan",
            priority=20,
            evidence_level="high",
        )
    ]


# 四件套 → 抗衰协议支柱(惰性 import 避免循环依赖;科学仍由各专家产出)
_PROTOCOL_PILLARS = [
    ("睡眠 / 恢复", "app.agents.recovery_coach.coach", "RecoveryCoachSpecialist"),
    ("营养", "app.agents.fuel_strategist.strategist", "FuelStrategistSpecialist"),
    ("运动", "app.agents.movement_coach.coach", "MovementCoachSpecialist"),
    ("压力 / 心理", "app.agents.mental_health_companion.companion", "MentalHealthCompanionSpecialist"),
]


def _compose_protocol(twin: HealthTwin) -> List[Dict[str, Any]]:
    """真实编排四件套:各跑一次,取其 summary 作该支柱的具体行动。

    自含(不依赖 orchestrator 是否跑过同伴),所以 analyze_longevity 工具 / 主动建卡
    场景也能拿到协议。任一专家失败 → 跳过该支柱,不影响整体(降级不假装)。
    recovery 先跑以拿 readiness_zone 传给 movement(与 orchestrator 同款依赖)。
    """
    import importlib

    pillars: List[Dict[str, Any]] = []
    ctx: Dict[str, Any] = {}
    for label, module_path, cls_name in _PROTOCOL_PILLARS:
        try:
            mod = importlib.import_module(module_path)
            sp = getattr(mod, cls_name)()
            finding = sp.run(twin, ctx)
            # recovery 把 readiness_zone 透给后续 movement(若产出)
            zone = (getattr(finding, "raw", None) or {}).get("readiness_zone")
            if zone:
                ctx["readiness_zone"] = zone
            action = (getattr(finding, "summary", "") or "").strip()
            if action:
                pillars.append({
                    "pillar": label,
                    "action": action,
                    "source": getattr(sp, "name", cls_name),
                })
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[longevity] protocol pillar {label} 失败 (跳过): {e}")
    return pillars


# LabsContext 字段名 → 中文展示名(用于"缺失输入"提示)
_PHENOAGE_INPUT_LABELS = {
    "albumin": "白蛋白(ALB)",
    "creatinine": "肌酐",
    "blood_glucose": "空腹血糖",
    "crp": "C 反应蛋白(CRP)",
    "lymphocyte_pct": "淋巴细胞百分比",
    "mcv": "红细胞平均体积(MCV)",
    "rdw": "红细胞分布宽度(RDW)",
    "alp": "碱性磷酸酶(ALP)",
    "wbc": "白细胞(WBC)",
}


def _cardio_signal(twin: HealthTwin, chrono: Optional[float]) -> Optional[Dict[str, Any]]:
    """第二生物年龄信号:VO2max / 体能年龄(全因死亡率最强单一预测因子)。

    chrono(实足年龄,来自 PhenoAge)已知时给出 fitness_age 与实足的差;
    未知时只给绝对值。设备估算值,evidence_tier=validated,不作诊断。
    """
    p = twin.physiological
    vo2 = p.vo2max_running or p.vo2max_cycling
    fit_age = p.vo2max_fitness_age
    if vo2 is None and fit_age is None:
        return None
    f: Dict[str, Any] = {
        "type": "cardio_fitness",
        "evidence_tier": "validated",
        "claim_boundary": (
            "VO2max / 体能年龄是心肺适能的设备估算值,是全因死亡率的强预测因子;"
            "反映可逆的有氧能力,不作诊断。"
        ),
        "note": "VO2max 是全因死亡率最强单一预测因子之一;有氧 + 抗阻训练可改善。",
    }
    if vo2 is not None:
        f["vo2max"] = round(float(vo2), 1)
    if fit_age is not None:
        f["fitness_age"] = int(fit_age)
        if chrono is not None:
            f["fitness_age_delta_years"] = round(int(fit_age) - chrono, 1)
    return f


def _missing_phenoage_inputs(twin: HealthTwin) -> List[str]:
    L = twin.labs
    missing: List[str] = []
    for key, label in _PHENOAGE_INPUT_LABELS.items():
        if getattr(L, key, None) is None:
            missing.append(label)
    return missing


def _interpret_delta(delta: Optional[float]) -> str:
    if delta is None:
        return ""
    if delta <= -3:
        return "明显年轻(身体年龄 < 实足年龄 ≥3 岁) — 维持当前生活方式即可。"
    if delta <= -1:
        return "略偏年轻(< 实足 1–3 岁)。"
    if delta < 1:
        return "接近实足年龄。"
    if delta < 3:
        return "略偏老化(> 实足 1–3 岁),关注下面的拖累项。"
    return "明显偏老化(> 实足 3 岁),建议系统性改善睡眠/运动/饮食/压力四件套。"


def _identify_drags(twin: HealthTwin) -> List[Dict[str, Any]]:
    """从 Twin 上读几个高 signal 的"明显异常"作为拖累项提示。

    这里只标"已知偏离参考区间"的指标,不做具体干预 — 干预走四件套。
    """
    L = twin.labs
    drags: List[Dict[str, Any]] = []

    # CRP 升高(炎症)→ 关联恢复/饮食
    if L.crp is not None and L.crp >= 0.3:  # mg/dL,临床通常 > 3 mg/L = 0.3 mg/dL 算升高
        drags.append({
            "metric": "crp",
            "value": L.crp,
            "unit": "mg/dL",
            "note": "炎症标志物升高",
        })
    # 空腹血糖
    if L.blood_glucose is not None and L.blood_glucose >= 6.1:
        drags.append({
            "metric": "blood_glucose",
            "value": L.blood_glucose,
            "unit": "mmol/L",
            "note": "空腹血糖偏高",
        })
    # LDL
    if L.ldl is not None and L.ldl >= 3.4:
        drags.append({
            "metric": "ldl",
            "value": L.ldl,
            "unit": "mmol/L",
            "note": "LDL 偏高",
        })
    # 血压
    if L.blood_pressure_systolic is not None and L.blood_pressure_systolic >= 130:
        drags.append({
            "metric": "blood_pressure_systolic",
            "value": L.blood_pressure_systolic,
            "unit": "mmHg",
            "note": "收缩压偏高",
        })
    # 睡眠
    sleep = twin.physiological.sleep_duration_h_latest
    if sleep is not None and sleep < 6.5:
        drags.append({
            "metric": "sleep_duration",
            "value": sleep,
            "unit": "h",
            "note": "睡眠时长不足",
        })

    return drags[:5]


def _compose_summary(
    pa: float,
    chrono: Optional[float],
    delta: Optional[float],
    drags: List[Dict[str, Any]],
) -> str:
    parts: List[str] = [f"表型年龄(PhenoAge) {pa} 岁"]
    if chrono is not None and delta is not None:
        sign = "+" if delta > 0 else ""
        parts.append(f"实足 {chrono} 岁 ({sign}{delta:.1f})")
    if drags:
        names = "/".join(d["metric"] for d in drags[:3])
        parts.append(f"可关注:{names}")
    return " · ".join(parts)
