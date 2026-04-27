"""
Metabolic Specialist —— 代谢健康综合管理。

覆盖：
- 血糖（空腹/HbA1c/CGM TIR）
- 血脂（LDL / HDL / 甘油三酯）
- 体重与 BMI
- 代谢综合征标记（腰围/血压/血脂三联）

整合 Twin.labs, Twin.cgm, Twin.body_composition, Twin.behavioral.diet_*.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, ProposedCard, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


def _metabolic_syndrome_criteria(twin: HealthTwin) -> Dict[str, Any]:
    """
    简化代谢综合征评估（IDF/NCEP ATP III 混合）:
      - 中心性肥胖 (BMI ≥ 28 作为简化替代)
      - 甘油三酯 ≥ 1.7 mmol/L
      - HDL < 1.0 (男) / < 1.3 (女)
      - 血压 ≥ 130/85
      - 空腹血糖 ≥ 5.6 mmol/L 或 HbA1c ≥ 5.7%

    满足 3 项以上为代谢综合征风险。
    """
    hits: List[str] = []
    body = twin.body_composition
    labs = twin.labs

    if body.bmi is not None and body.bmi >= 28:
        hits.append(f"BMI {body.bmi:.1f}")
    if labs.triglycerides is not None and labs.triglycerides >= 1.7:
        hits.append(f"甘油三酯 {labs.triglycerides}")
    if labs.hdl is not None and labs.hdl < 1.0:
        hits.append(f"HDL {labs.hdl} 偏低")
    if (labs.blood_pressure_systolic or 0) >= 130 or (labs.blood_pressure_diastolic or 0) >= 85:
        hits.append(f"BP {labs.blood_pressure_systolic}/{labs.blood_pressure_diastolic}")
    if (labs.blood_glucose or 0) >= 5.6 or (labs.hba1c or 0) >= 5.7:
        hits.append("空腹血糖/HbA1c 偏高")

    return {"criteria_hit": len(hits), "factors": hits, "is_metabolic_syndrome": len(hits) >= 3}


class MetabolicSpecialist:
    name = "metabolic_specialist"
    category = "chronic"

    TRIGGER_KEYWORDS = {
        "代谢", "血糖", "血脂", "体重", "减重", "减肥",
        "糖尿病", "糖化", "胆固醇", "甘油三酯",
        "diabetes", "metabolic", "weight loss", "cholesterol",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "chronic" in intent.categories or "fuel" in intent.categories:
            return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 兜底：化验或 CGM 数据存在
        if twin.labs.hba1c or twin.labs.hdl or twin.cgm.has_cgm:
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            findings: List[Dict[str, Any]] = []
            summary_parts: List[str] = []

            # 1. 血糖
            labs = twin.labs
            if labs.hba1c is not None:
                findings.append({
                    "type": "hba1c",
                    "value": labs.hba1c,
                    "status": _hba1c_status(labs.hba1c),
                })
                summary_parts.append(f"HbA1c {labs.hba1c}")
            elif labs.blood_glucose is not None:
                findings.append({
                    "type": "fasting_glucose",
                    "value": labs.blood_glucose,
                    "status": _glucose_status(labs.blood_glucose),
                })
                summary_parts.append(f"空腹血糖 {labs.blood_glucose}")

            # 2. CGM 摘要（如有）
            if twin.cgm.has_cgm and twin.cgm.tir_24h_pct is not None:
                findings.append({
                    "type": "cgm_summary",
                    "tir_pct": twin.cgm.tir_24h_pct,
                    "mean_mg_dl": twin.cgm.mean_24h_mg_dl,
                    "gmi": twin.cgm.gmi_estimated_a1c,
                    "cv_pct": twin.cgm.cv_24h_pct,
                })
                summary_parts.append(f"CGM TIR {twin.cgm.tir_24h_pct:.0f}%")

            # 3. 血脂
            lipid_parts = []
            if labs.ldl is not None:
                lipid_parts.append(f"LDL {labs.ldl}")
            if labs.hdl is not None:
                lipid_parts.append(f"HDL {labs.hdl}")
            if labs.triglycerides is not None:
                lipid_parts.append(f"TG {labs.triglycerides}")
            if lipid_parts:
                findings.append({
                    "type": "lipid_panel",
                    "ldl": labs.ldl,
                    "hdl": labs.hdl,
                    "triglycerides": labs.triglycerides,
                })
                summary_parts.append(" / ".join(lipid_parts))

            # 4. 体重 / BMI
            body = twin.body_composition
            if body.bmi is not None:
                findings.append({
                    "type": "body_composition",
                    "bmi": body.bmi,
                    "bmi_category": body.bmi_category,
                    "weight_kg": body.weight_kg,
                    "body_fat_pct": body.body_fat_pct,
                })
                summary_parts.append(f"BMI {body.bmi:.1f}")

            # 5. 代谢综合征
            ms = _metabolic_syndrome_criteria(twin)
            if ms["criteria_hit"] > 0:
                findings.append({
                    "type": "metabolic_syndrome",
                    "criteria_hit": ms["criteria_hit"],
                    "factors": ms["factors"],
                    "is_metabolic_syndrome": ms["is_metabolic_syndrome"],
                })

            # 6. 能量平衡（来自 Fuel Strategist 的输入复用）
            if body.tdee_kcal and twin.behavioral.diet_calories_today:
                deficit = body.tdee_kcal - twin.behavioral.diet_calories_today
                findings.append({
                    "type": "energy_balance",
                    "tdee_kcal": body.tdee_kcal,
                    "intake_kcal": twin.behavioral.diet_calories_today,
                    "remaining_kcal": round(deficit, 0),
                })

            # 7. 行动建议
            actions = _metabolic_actions(twin, ms)
            for i, a in enumerate(actions, 1):
                findings.append({"type": "action", "order": i, "text": a})

            summary = " · ".join(summary_parts) if summary_parts else "代谢数据暂缺"
            if ms["is_metabolic_syndrome"]:
                summary = "⚠️ 代谢综合征 · " + summary

            # 信任循环: LDL > 3.4 / HbA1c > 5.7 / TG > 1.7 → 各产 1 张
            proposed_cards: List[ProposedCard] = []
            if labs.ldl is not None and labs.ldl > 3.4:
                target = round(max(2.6, labs.ldl - 0.5), 1)
                proposed_cards.append(ProposedCard(
                    title=f"60 天降 LDL：{labs.ldl} → ≤ {target} mmol/L",
                    content=(
                        f"## 60 天降 LDL 实验\n\n"
                        f"**起点**: LDL {labs.ldl} mmol/L\n"
                        f"**目标**: 60 天后 LDL ≤ {target} mmol/L\n\n"
                        f"### 行动 (饮食结构性改变)\n"
                        f"- 饱和脂肪 < 7% 总热量 (减红肉/全脂奶/椰子油)\n"
                        f"- 每日可溶性纤维 ≥ 10g (燕麦/豆类/苹果)\n"
                        f"- 植物甾醇 2g/天 (强化食品或胶囊)\n"
                        f"- 每周有氧 ≥ 150 分钟\n\n"
                        f"60 天后系统按最新化验值评分。"
                    ),
                    metric_key="ldl",
                    baseline_value=str(labs.ldl),
                    target_value=f"<={target}",
                    verification_days=60,
                    card_type="plan",
                    priority=15,
                ))
            if labs.hba1c is not None and labs.hba1c >= 5.7:
                target = round(max(5.4, labs.hba1c - 0.3), 1)
                proposed_cards.append(ProposedCard(
                    title=f"90 天降 HbA1c：{labs.hba1c} → ≤ {target}%",
                    content=(
                        f"## 90 天降糖化血红蛋白实验\n\n"
                        f"**起点**: HbA1c {labs.hba1c}%\n"
                        f"**目标**: 90 天后 HbA1c ≤ {target}%\n\n"
                        f"### 行动\n"
                        f"- 减少精制碳水, 主食至少 1/3 替换全谷/豆类\n"
                        f"- 餐后 10 分钟散步 (降餐后血糖)\n"
                        f"- 每周 ≥ 2 次抗阻训练 (改善肌肉胰岛素敏感性)\n"
                        f"- 限糖饮料 / 果汁\n\n"
                        f"HbA1c 反映近 90 天平均血糖, 评分窗口 90 天。"
                    ),
                    metric_key="hba1c",
                    baseline_value=str(labs.hba1c),
                    target_value=f"<={target}",
                    verification_days=90,
                    card_type="plan",
                    priority=18,
                ))
            if labs.triglycerides is not None and labs.triglycerides >= 1.7:
                target = 1.5
                proposed_cards.append(ProposedCard(
                    title=f"30 天降 TG：{labs.triglycerides} → ≤ {target} mmol/L",
                    content=(
                        f"## 30 天降甘油三酯实验\n\n"
                        f"**起点**: TG {labs.triglycerides} mmol/L\n"
                        f"**目标**: 30 天后 TG ≤ {target}\n\n"
                        f"### 行动\n"
                        f"- 限糖 / 限酒 (TG 对糖和酒最敏感)\n"
                        f"- Omega-3 (鱼油 EPA+DHA 2-4g/天)\n"
                        f"- 减重 5% (如有空间)\n"
                        f"- 每周 ≥ 3 次有氧运动\n"
                    ),
                    metric_key="tg",
                    baseline_value=str(labs.triglycerides),
                    target_value=f"<={target}",
                    verification_days=30,
                    card_type="plan",
                    priority=14,
                ))

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "metabolic_syndrome": ms["is_metabolic_syndrome"],
                    "criteria_hit": ms["criteria_hit"],
                    "hba1c": labs.hba1c,
                    "bmi": body.bmi,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
                proposed_cards=proposed_cards,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[metabolic_specialist] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"代谢评估失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )


def _hba1c_status(v: float) -> str:
    if v >= 6.5:
        return "diabetes"
    if v >= 5.7:
        return "prediabetes"
    return "normal"


def _glucose_status(v: float) -> str:
    if v >= 7.0:
        return "diabetes"
    if v >= 5.6:
        return "impaired"
    return "normal"


def _metabolic_actions(twin: HealthTwin, ms: Dict[str, Any]) -> List[str]:
    actions: List[str] = []

    if ms["is_metabolic_syndrome"]:
        actions.append("代谢综合征需要综合干预：减重 5-10% 可同时改善血糖、血压、血脂。")

    hba1c = twin.labs.hba1c
    if hba1c is not None:
        if hba1c >= 6.5:
            actions.append("HbA1c 达糖尿病标准，就诊内分泌科启动系统化管理。")
        elif hba1c >= 5.7:
            actions.append("前期阶段可逆转：每周 150 分钟中等强度有氧 + 减重 5-7%，3-6 月复查。")

    ldl = twin.labs.ldl
    if ldl and ldl >= 4.1:
        actions.append("LDL 偏高，采用地中海饮食（橄榄油、鱼、坚果、蔬果）3 个月后复查。")

    if (twin.body_composition.bmi or 0) >= 28:
        actions.append("BMI 偏高，建议结合 CGM / 体重记录，目标每周减 0.5-1 kg（不超过）。")

    if twin.cgm.has_cgm and (twin.cgm.tir_24h_pct or 100) < 70:
        actions.append("CGM TIR 未达标：识别餐后高峰时段，调整餐前运动 / 低 GI 饮食。")

    if not actions:
        actions.append("代谢指标目前平稳，继续当前饮食运动节奏。")

    return actions[:5]
