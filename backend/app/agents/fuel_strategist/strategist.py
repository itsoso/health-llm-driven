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

from app.orchestrator.schema import Intent, SpecialistFinding
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
    """从 Twin.genetic 派生营养提示。"""
    nudges: List[Dict[str, str]] = []
    all_variants = (
        (twin.genetic.drug_sensitivity or [])
        + (twin.genetic.risk_variants or [])
        + (twin.genetic.protective_variants or [])
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

    # MTHFR: 甲基叶酸
    if _has_risk("MTHFR"):
        nudges.append({
            "gene": "MTHFR",
            "tip": "叶酸代谢效率下降，优先从深绿叶蔬（菠菜/芦笋/甘蓝）+ 甲基叶酸补剂获取，而非合成叶酸。",
        })

    # APOE4: 饱和脂肪敏感
    v_apoe = by_gene.get("APOE")
    if v_apoe and "4" in (v_apoe.get("genotype") or ""):
        nudges.append({
            "gene": "APOE",
            "tip": "APOE4 携带者对饱和脂肪敏感，增加橄榄油/鱼油替代红肉脂肪，LDL 目标更严格。",
        })

    # FTO: 食欲调节
    if _has_risk("FTO"):
        nudges.append({
            "gene": "FTO",
            "tip": "FTO 风险型对高蛋白餐更敏感：每餐保证 25-35g 蛋白，避免单纯高碳水餐导致血糖波动。",
        })

    # LCT: 乳糖不耐
    v_lct = by_gene.get("LCT") or by_gene.get("MCM6")
    if v_lct and ("CC" in (v_lct.get("genotype") or "") or _has_risk("LCT")):
        nudges.append({
            "gene": "LCT/MCM6",
            "tip": "乳糖吸收能力下降，选酸奶/硬奶酪/无乳糖奶替代普通牛奶。",
        })

    return nudges[:3]


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

            # 7. 代谢异常标记
            abnormal_names = [
                a.get("item_name")
                for a in (twin.labs.flagged_abnormal or [])
                if a.get("item_name") in (
                    "LDL", "低密度脂蛋白", "甘油三酯", "血糖", "HbA1c",
                    "糖化血红蛋白", "谷丙转氨酶", "谷草转氨酶",
                )
            ]
            if abnormal_names:
                findings.append({
                    "type": "labs_concern",
                    "items": abnormal_names,
                })

            summary = " · ".join(summary_parts) or "数据暂缺，无法评估营养状态"

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
