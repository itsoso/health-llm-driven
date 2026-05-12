"""
Fuel Strategist —— 营养与补水策略。

核心计算：
- 剩余热量 = TDEE - 今日摄入
- 蛋白进度 = 今日蛋白 / (1.6 × 体重kg)    [运动人群目标 1.6-2.2 g/kg]
- 水进度   = 今日水 / 目标水
- 基因驱动的饮食提示（MTHFR / APOE / FTO / ALDH2 / LCT）

返回结构化 finding，具体措施留给下游 orchestrator 去 LLM 合成。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, ProposedCard, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


# ─────────────────────── 工具 ────────────────────────


def _safe(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _protein_target_g(weight_kg: Optional[float], training_load_7d: Optional[float]) -> Optional[float]:
    """训练活跃人群用 1.8 g/kg；低活动用 1.4 g/kg。"""
    if weight_kg is None:
        return None
    factor = 1.8 if (training_load_7d or 0) > 200 else 1.4
    return weight_kg * factor


def _meal_slot_now() -> str:
    """当前时间对应的下一餐槽位。"""
    h = datetime.now().hour
    if 5 <= h < 10:
        return "早餐"
    if 10 <= h < 14:
        return "午餐"
    if 14 <= h < 18:
        return "下午加餐"
    if 18 <= h < 21:
        return "晚餐"
    return "夜宵/睡前补充"


# ─────────────────────── 基因驱动的饮食提示 ────────────────


def _gene_nudges(twin: HealthTwin) -> List[Dict[str, str]]:
    """从 GeneConfig 派生营养提示。有 GeneConfig 时使用结构化参数，否则回退原始解析。"""
    nudges: List[Dict[str, str]] = []
    gc = twin.gene_config

    if gc and gc.has_data:
        if gc.methylation != "normal":
            nudges.append({
                "gene": "MTHFR",
                "tip": f"甲基化{gc.methylation}，必须使用{gc.folate_form}（甲基叶酸），而非合成叶酸。深绿叶蔬（菠菜/芦笋/甘蓝）是天然来源。",
            })
        if gc.saturated_fat_sensitivity == "high":
            nudges.append({
                "gene": "APOE",
                "tip": f"APOE {gc.apoe_type or '4型'} 携带者，对饱和脂肪高度敏感。用橄榄油/鱼油替代红肉脂肪，LDL目标比常人更严格。",
            })
        if gc.obesity_risk == "elevated":
            nudges.append({
                "gene": "FTO",
                "tip": "FTO 风险型：每餐保证25-35g蛋白质，避免单纯高碳水餐，增加膳食纤维延缓血糖波动。",
            })
        if not gc.lactose_tolerant:
            nudges.append({
                "gene": "LCT",
                "tip": "乳糖不耐受，选酸奶/硬奶酪/无乳糖奶替代普通牛奶。",
            })
        if gc.omega3_conversion == "reduced":
            nudges.append({
                "gene": "FADS1",
                "tip": "Omega-3转化效率低，需直接补充EPA/DHA（深海鱼≥3次/周或鱼油≥1g/d）。",
            })
        if gc.alcohol_metabolism == "deficient":
            nudges.append({
                "gene": "ALDH2",
                "tip": "酒精代谢缺陷，饮酒后乙醛蓄积，严格限酒。食管癌风险增高。",
            })
        if gc.antioxidant_capacity == "reduced":
            nudges.append({
                "gene": "SOD2/GPX1",
                "tip": "抗氧化能力下降，增加蓝莓/深色蔬菜/绿茶，补充CoQ10/虾青素。",
            })
        if gc.caffeine_metabolism == "slow":
            nudges.append({
                "gene": "CYP1A2",
                "tip": "咖啡因慢代谢，下午14:00后避免咖啡/茶，以免影响睡眠质量。",
            })
        return nudges

    # 回退：无 GeneConfig 时使用原始变异解析
    all_variants = (
        (twin.genetic.drug_sensitivity or [])
        + (twin.genetic.risk_variants or [])
        + (twin.genetic.protective_variants or [])
        + (twin.genetic.nutrition_variants or [])
        + (twin.genetic.recovery_variants or [])
    )

    by_gene: Dict[str, Dict[str, Any]] = {}
    for v in all_variants:
        name = (v.get("gene_name") or "").upper()
        if name:
            by_gene.setdefault(name, v)

    def _has_risk(name: str) -> bool:
        v = by_gene.get(name)
        if not v:
            return False
        label = (v.get("result_label") or "").lower()
        risk = (v.get("risk_level") or "").lower()
        geno = (v.get("genotype") or "").upper()
        return (
            "risk" in risk
            or "高" in risk
            or "中" in risk
            or "poor" in label
            or "reduced" in label
            or "TT" in geno
            or "CC" in geno
        )

    if _has_risk("MTHFR"):
        nudges.append({"gene": "MTHFR", "tip": "叶酸代谢效率下降，优先从深绿叶蔬 + 甲基叶酸补剂获取。"})
    v_apoe = by_gene.get("APOE")
    if v_apoe and "4" in (v_apoe.get("genotype") or ""):
        nudges.append({"gene": "APOE", "tip": "APOE4携带者对饱和脂肪敏感，增加橄榄油/鱼油替代红肉脂肪。"})
    if _has_risk("FTO"):
        nudges.append({"gene": "FTO", "tip": "FTO风险型，每餐保证25-35g蛋白，避免单纯高碳水餐。"})
    if _has_risk("FADS1"):
        nudges.append({"gene": "FADS1", "tip": "Omega-3转化效率低，需更多直接EPA/DHA来源。"})
    if _has_risk("ALDH2"):
        nudges.append({"gene": "ALDH2", "tip": "乙醛脱氢酶缺陷，严格限酒。"})
    if _has_risk("SOD2"):
        nudges.append({"gene": "SOD2", "tip": "抗氧化能力弱，增加抗氧化食物+CoQ10。"})

    return nudges

    gstp1 = by_gene.get("GSTP1")
    if gstp1 and (gstp1.get("risk_level") or "").lower() in ("medium", "high"):
        nudges.append({
            "gene": "GSTP1",
            "tip": "Phase II解毒酶效率低→多吃十字花科蔬菜(西兰花/萝卜硫素)支持肝脏解毒。",
        })

    return nudges[:5]


# ─────────────────────── Specialist ────────────────────


class FuelStrategistSpecialist:
    name = "fuel_strategist"
    category = "fuel"

    TRIGGER_KEYWORDS = {
        "吃什么", "饮食", "营养", "热量", "卡路里", "蛋白",
        "碳水", "脂肪", "晚餐", "早餐", "午餐", "吃饭",
        "补剂", "喝水", "补水", "饿", "饱",
        "diet", "nutrition", "protein", "carb", "fuel", "eat",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "fuel" in intent.categories:
            return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 兜底：dashboard 场景下有饮食或身体组成数据就参与
        if "general" in intent.categories and (
            twin.behavioral.meals_logged_today or twin.body_composition.tdee_kcal
        ):
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            findings: List[Dict[str, Any]] = []
            summary_parts: List[str] = []

            b = twin.behavioral
            body = twin.body_composition

            # 1. 能量缺口
            tdee = _safe(body.tdee_kcal)
            intake = _safe(b.diet_calories_today)
            if tdee is not None and intake is not None:
                remaining = tdee - intake
                progress = intake / tdee * 100.0 if tdee > 0 else 0
                findings.append({
                    "type": "energy",
                    "tdee_kcal": tdee,
                    "intake_kcal": intake,
                    "remaining_kcal": round(remaining, 0),
                    "progress_pct": round(progress, 0),
                    "meals_logged": b.meals_logged_today,
                })
                summary_parts.append(
                    f"热量 {int(intake)}/{int(tdee)} kcal ({int(progress)}%)"
                )

            # 2. 蛋白进度
            protein_today = _safe(b.diet_protein_g_today)
            protein_target = _protein_target_g(body.weight_kg, b.training_load_7d)
            if protein_today is not None and protein_target:
                pct = protein_today / protein_target * 100.0
                findings.append({
                    "type": "protein",
                    "today_g": protein_today,
                    "target_g": round(protein_target, 0),
                    "progress_pct": round(pct, 0),
                })
                summary_parts.append(
                    f"蛋白 {int(protein_today)}/{int(protein_target)}g ({int(pct)}%)"
                )

            # 3. 饮水
            water_ml = b.water_ml_today or 0
            water_goal = b.water_goal_ml or 2000
            water_pct = water_ml / water_goal * 100.0 if water_goal > 0 else 0
            findings.append({
                "type": "hydration",
                "ml_today": water_ml,
                "goal_ml": water_goal,
                "progress_pct": round(water_pct, 0),
                "status": "low" if water_pct < 50 else ("ok" if water_pct < 90 else "full"),
            })
            summary_parts.append(f"水 {water_ml}/{water_goal}ml")

            # 4. 下一餐槽位
            slot = _meal_slot_now()
            findings.append({
                "type": "next_meal",
                "slot": slot,
                "guidance": _next_meal_guidance(slot, findings),
            })

            # 5. 补剂完成度
            if twin.supplement.total_active_count > 0:
                findings.append({
                    "type": "supplement",
                    "taken_today": twin.supplement.taken_today_count,
                    "total": twin.supplement.total_active_count,
                    "pending": [
                        s.get("name")
                        for s in (twin.supplement.active_supplements or [])
                        if not s.get("taken")
                    ][:5],
                })

            # 6. 基因驱动的提示
            nudges = _gene_nudges(twin)
            for n in nudges:
                findings.append({"type": "gene_nudge", **n})

            # 7. 代谢异常标记 (按 item_name 去重, 多次复查同一指标只显示一次)
            seen_lab = set()
            abnormal_names: List[str] = []
            for a in (twin.labs.flagged_abnormal or []):
                name = a.get("item_name")
                if name in (
                    "LDL", "低密度脂蛋白", "甘油三酯", "血糖", "HbA1c",
                    "糖化血红蛋白", "谷丙转氨酶", "谷草转氨酶",
                ) and name not in seen_lab:
                    seen_lab.add(name)
                    abnormal_names.append(name)
            if abnormal_names:
                findings.append({
                    "type": "labs_concern",
                    "items": abnormal_names,
                })

            summary = " · ".join(summary_parts) or "数据暂缺，无法评估营养状态"

            # 信任循环: 如果体重 + 减重诉求明确, 提一个 14 天减重 0.7kg 的可验证假设
            proposed_cards: List[ProposedCard] = []
            cur_weight = body.weight_kg
            target_weight = getattr(twin.goals, "target_weight_kg", None) if hasattr(twin, "goals") else None
            if cur_weight and target_weight and cur_weight > target_weight + 0.5:
                # 14 天减 0.7kg 是 -350kcal/天 的安全节奏
                step_target = round(cur_weight - 0.7, 1)
                proposed_cards.append(ProposedCard(
                    title=f"14 天减重实验：{cur_weight:g} → {step_target}kg",
                    content=(
                        f"## 14 天减重小步实验\n\n"
                        f"**起点**: {cur_weight}kg → **目标**: {step_target}kg (减 0.7kg)\n\n"
                        f"### 行动\n"
                        f"- 每日热量缺口 350-400 kcal (TDEE 估 {int(tdee) if tdee else '~2200'} kcal)\n"
                        f"- 蛋白每日 ≥ {int(protein_target) if protein_target else int((cur_weight or 70)*1.6)}g\n"
                        f"- 每日饮水 ≥ {water_goal}ml\n"
                        f"- 每周 3 次有氧 + 2 次抗阻\n\n"
                        f"14 天后系统用最新体重数据自动评分。"
                    ),
                    metric_key="weight",
                    baseline_value=str(cur_weight),
                    target_value=f"<{step_target}",
                    verification_days=14,
                    card_type="plan",
                    priority=14,
                ))
            elif cur_weight and (
                # 没有减重目标 / 已经在目标 ±0.5kg 内 → 押 forecast: "7 天体重稳定"
                target_weight is None or abs(cur_weight - target_weight) <= 0.5
            ):
                # forecast: 7 天体重不会突涨 (>0.5kg). target=cur+0.5 表示
                # "实际 < cur+0.5" 才算命中. 这要求 grader direction='<'.
                # cur_weight 和 floor 都用 1 位小数, 避免 "70.4kg" → "70" 截断歧义
                floor_w = round(cur_weight + 0.5, 1)
                proposed_cards.append(ProposedCard(
                    title=f"AI 预测: 7 天体重保持 ≤ {floor_w}kg",
                    content=(
                        f"## AI 预测\n\n"
                        f"**当前**: 体重 {cur_weight}kg"
                        f"{f' (距目标 {target_weight}kg 仅 {abs(cur_weight - target_weight):.1f}kg)' if target_weight else ''}\n"
                        f"**预测**: 7 天后体重 ≤ {floor_w}kg (即不超 +0.5kg)\n\n"
                        f"这是一条 *纯预测* — 你按当前饮食节奏即可, AI 押注体重不会突涨.\n"
                        f"7 天后系统自动用最新体重数据评分.\n"
                    ),
                    metric_key="weight",
                    baseline_value=str(cur_weight),
                    target_value=f"<{floor_w}",
                    verification_days=7,
                    card_type="forecast",
                    priority=7,  # 低于 plan, 状态稳时不抢真问题位置
                ))

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "intake_kcal": intake,
                    "tdee_kcal": tdee,
                    "protein_today_g": protein_today,
                    "water_pct": round(water_pct, 0),
                    "meal_slot": slot,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
                proposed_cards=proposed_cards,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[fuel_strategist] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"营养评估失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )


def _next_meal_guidance(slot: str, current_findings: List[Dict[str, Any]]) -> str:
    """根据餐槽位 + 当前缺口生成一句建议。"""
    # 找到 energy 和 protein finding
    energy = next((f for f in current_findings if f.get("type") == "energy"), None)
    protein = next((f for f in current_findings if f.get("type") == "protein"), None)

    parts: List[str] = []
    if energy and energy.get("remaining_kcal") is not None:
        remaining = energy["remaining_kcal"]
        if remaining > 600:
            parts.append(f"还有 {int(remaining)} kcal 空间，正餐可以安排")
        elif remaining > 200:
            parts.append(f"剩 {int(remaining)} kcal，适合一餐轻食")
        elif remaining > 0:
            parts.append(f"剩 {int(remaining)} kcal，建议低热量高纤维补充")
        else:
            parts.append(f"今日已超出热量 {int(-remaining)} kcal，建议加强运动或减少下一餐")

    if protein and protein.get("progress_pct", 100) < 60:
        parts.append(
            f"蛋白还差 {int((protein['target_g'] - protein['today_g']))}g，"
            "下一餐优先一拳大小的鱼/鸡/蛋/豆腐"
        )

    base = f"【{slot}】" + ("；".join(parts) if parts else "按正常份量安排即可")
    return base
