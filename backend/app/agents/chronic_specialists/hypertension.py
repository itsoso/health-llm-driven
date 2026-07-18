"""
Hypertension (高血压) Specialist。

核心理念：高血压管理的黄金三角是 **监测 + 生活方式 + 药物依从**。

输入：
- twin.labs.blood_pressure_systolic / diastolic
- twin.behavioral.water_ml_today, workouts_this_week
- twin.medication.active_meds（降压药识别）
- twin.body_composition.weight_kg, bmi
- twin.mental.stress_7d_avg
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, ProposedCard, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


# 简单分级（ACC/AHA 2017）
def _bp_stage(sys_bp: Optional[int], dia_bp: Optional[int]) -> str:
    if sys_bp is None and dia_bp is None:
        return "unknown"
    s = sys_bp or 0
    d = dia_bp or 0
    if s >= 180 or d >= 120:
        return "severe"
    if s >= 140 or d >= 90:
        return "stage2"
    if s >= 130 or d >= 80:
        return "stage1"
    if s >= 120:
        return "elevated"
    return "normal"


def _has_antihypertensive(twin: HealthTwin) -> List[str]:
    keywords = [
        "普利", "pril", "沙坦", "sartan",
        "洛尔", "olol", "地平", "dipine",
        "氢氯噻嗪", "hctz", "呋塞米",
        "缬沙坦", "valsartan", "氯沙坦",
    ]
    hits = []
    for m in twin.medication.active_meds or []:
        name = (m.get("name") or "").lower()
        for k in keywords:
            if k in name:
                hits.append(m.get("name"))
                break
    return hits


class HypertensionSpecialist:
    name = "hypertension_specialist"
    category = "chronic"

    TRIGGER_KEYWORDS = {
        "血压", "高血压", "降压", "hypertension", "bp", "blood pressure",
        "普利", "沙坦", "洛尔", "地平",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "chronic" in intent.categories:
            return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 兜底：BP 偏高或在服降压药
        sys_bp = twin.labs.blood_pressure_systolic
        if sys_bp and sys_bp >= 130:
            return True
        if _has_antihypertensive(twin):
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            sys_bp = twin.labs.blood_pressure_systolic
            dia_bp = twin.labs.blood_pressure_diastolic
            stage = _bp_stage(sys_bp, dia_bp)
            antihyper = _has_antihypertensive(twin)

            # 2026-05-13: 数据缺口 short-circuit — 没 BP 数据 + 没在服降压药
            # 不让 LLM 合成"血压可能..." 这种没事实根据的话.
            if stage == "unknown" and not antihyper:
                return SpecialistFinding(
                    specialist_name=self.name,
                    category=self.category,
                    summary="需补充: 暂无血压数据, 也未识别在服降压药",
                    findings=[
                        {
                            "type": "data_gap",
                            "missing": ["blood_pressure_systolic", "blood_pressure_diastolic"],
                            "hint": "请测一次血压并记录, 我才能给出针对性建议",
                        },
                        {
                            "type": "action",
                            "order": 1,
                            "text": "请测一次血压 (静息 5 分钟后, 早晨较好), 在 App 里记录或上传体检单. 数据齐了我再来分析.",
                        },
                    ],
                    raw={"stage": "unknown", "data_gap": True},
                    ms_elapsed=int((time.monotonic() - t0) * 1000),
                )

            findings: List[Dict[str, Any]] = []
            summary_parts: List[str] = []

            findings.append({
                "type": "bp_status",
                "systolic": sys_bp,
                "diastolic": dia_bp,
                "stage": stage,
                "date": str(twin.labs.blood_pressure_date) if twin.labs.blood_pressure_date else None,
            })

            stage_zh = {
                "normal": "正常",
                "elevated": "血压偏高",
                "stage1": "一级高血压",
                "stage2": "二级高血压",
                "severe": "血压严重升高",
                "unknown": "未测量",
            }[stage]
            if sys_bp and dia_bp:
                summary_parts.append(f"血压 {sys_bp}/{dia_bp} · {stage_zh}")
            else:
                summary_parts.append(stage_zh)

            if antihyper:
                findings.append({
                    "type": "active_antihypertensives",
                    "meds": antihyper,
                })
                summary_parts.append(f"在服降压药 {len(antihyper)} 种")

            # 生活方式评估
            lifestyle_notes = []
            if twin.body_composition.bmi and twin.body_composition.bmi >= 25:
                lifestyle_notes.append(
                    f"BMI {twin.body_composition.bmi:.1f} 偏高，减重 5-10% 可以降 SBP 约 5-20 mmHg"
                )
            if (twin.behavioral.workouts_this_week or 0) < 3:
                lifestyle_notes.append("每周有氧 < 3 次，增加到 5 次以上可以降 SBP 约 4-9 mmHg")
            if twin.mental.stress_7d_avg and twin.mental.stress_7d_avg >= 7:
                lifestyle_notes.append("压力偏高会拉高血压，每日 10 分钟冥想/呼吸训练有可测效果")

            for note in lifestyle_notes:
                findings.append({"type": "lifestyle_note", "text": note})

            # 行动
            actions = _actions_for_stage(stage, bool(antihyper))
            for i, a in enumerate(actions, 1):
                findings.append({"type": "action", "order": i, "text": a})

            # 信任循环: stage1+ 给一个 14 天降压实验
            proposed_cards: List[ProposedCard] = []
            if stage in {"elevated", "stage1", "stage2"} and sys_bp:
                # 目标 SBP: stage2 -10mmHg, stage1 -7mmHg, elevated -5mmHg, 但不低于 115
                drop = {"stage2": 10, "stage1": 7, "elevated": 5}[stage]
                target = max(115, sys_bp - drop)
                proposed_cards.append(ProposedCard(
                    title=f"14 天降压实验：SBP {sys_bp} → ≤ {target}",
                    content=(
                        f"## 14 天降压小步实验\n\n"
                        f"**起点**: SBP {sys_bp} / DBP {dia_bp} ({stage_zh})\n"
                        f"**目标**: 14 天后 SBP ≤ {target}\n\n"
                        f"### 行动 (DASH + ACC/AHA 共识)\n"
                        f"- 钠摄入 < 2.3g/天 (尽量 < 1.5g)\n"
                        f"- 每周有氧 ≥ 150 分钟 (快走/游泳/骑车)\n"
                        f"- 限酒 (男 ≤ 2 杯/天, 女 ≤ 1 杯)\n"
                        f"- 每天测 1 次 BP, 早晨起床 30 分钟内\n"
                        f"{'- 按医嘱规律服降压药' if antihyper else '- 如复测 SBP 始终 ≥ 140, 联系医生'}\n\n"
                        f"14 天后系统用最近 BP 数据自动评分。"
                    ),
                    metric_key="systolic_bp",
                    baseline_value=str(sys_bp),
                    target_value=f"<={target}",
                    verification_days=14,
                    card_type="plan",
                    priority=18,
                ))

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=" · ".join(summary_parts),
                findings=findings,
                raw={
                    "stage": stage,
                    "systolic": sys_bp,
                    "diastolic": dia_bp,
                    "has_med": bool(antihyper),
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
                proposed_cards=proposed_cards,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[hypertension_specialist] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"高血压评估失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )


def _actions_for_stage(stage: str, has_med: bool) -> List[str]:
    if stage == "severe":
        return [
            "停止剧烈活动，静坐至少 1 分钟后复测并记录结果。",
            "若复测仍处于严重升高范围，尽快联系医疗专业人员；如伴胸痛、气促、背痛、麻木或无力、视力改变或说话困难，立即拨打急救电话。",
        ]
    if stage == "stage2":
        return [
            "1 周内复测 3 次（同一时间、静息 5 分钟后）并记录平均值。",
            "就诊内科或心内科评估是否需要启动/调整降压药。",
            "立即限盐（<5g/日）、增加运动、控制体重。",
        ]
    if stage == "stage1":
        return [
            "生活方式干预为主：DASH 饮食、每周 150 分钟中等强度有氧、限盐限酒。",
            "3 个月后复查，如仍 ≥130/80 考虑药物治疗。",
        ]
    if stage == "elevated":
        return [
            "生活方式优化：低钠饮食、规律运动、减重、压力管理。",
            "每季度复测一次，关注是否继续升高。",
        ]
    if stage == "normal":
        if has_med:
            return [
                "血压控制良好，继续保持当前方案。",
                "不要自行停药 —— 血压稳定是因为药物，停药会反弹。",
                "定期复诊评估是否可以维持或调整。",
            ]
        return ["血压正常，继续保持健康生活方式。"]
    return ["建议定期测量血压并记录，作为长期趋势参考。"]
