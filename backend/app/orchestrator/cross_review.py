"""
Multi-Agent Cross-Review — specialist 之间的"协商"层.

问题: 现在 10 个 specialist 各跑各的, finding 直接拼给 LLM 合成. 但真实
医疗思考是有交叉的:
  - FuelStrategist 推荐高蛋白饮食
  - MetabolicSpecialist 看 user 肌酐 145 → 高蛋白饮食有肾脏风险
  → 矛盾应被发现 + escalate, 而不是两个建议并列输出.

设计:
1. 确定性 conflict_rules: 编码常见的 specialist 间冲突
   (营养 vs 慢病 / 训练 vs 恢复 / 补剂 vs 药物 等)
2. 检测到冲突 → 给 finding 加 conflict_flag + 矛盾说明
3. orchestrator 合成 prompt 把冲突放在最显眼位置, 强制 LLM 明示决策依据
4. 不引入额外 LLM 调用 (省 token), 全靠规则

未来 v2: 真正"specialist 互相 review 对方 finding" 的 LLM debate, 但成本翻倍.
v1 用确定性规则覆盖 80% 高频冲突就足够形成"协作感".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


@dataclass
class Conflict:
    """两个 specialist finding 之间的矛盾."""
    specialist_a: str
    specialist_b: str
    severity: str  # 'soft' | 'hard'
    description: str
    resolution_hint: str


# ─────────────────────── 规则 ───────────────────────


def _get_finding(findings: List[SpecialistFinding], name: str) -> Optional[SpecialistFinding]:
    return next((f for f in findings if f.specialist_name == name), None)


def _has_proposed_metric(f: Optional[SpecialistFinding], metric: str) -> bool:
    if not f:
        return False
    return any(pc.metric_key == metric for pc in (f.proposed_cards or []))


def _check_protein_vs_kidney(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """FuelStrategist 推高蛋白 + 肌酐偏高 → 冲突."""
    conflicts = []
    fuel = _get_finding(findings, "fuel_strategist")
    if not fuel:
        return conflicts

    # 看 fuel 输出是否暗示高蛋白
    fuel_text = (fuel.summary or "") + " " + " ".join(
        str(f.get("text", "") or "") for f in fuel.findings
    )
    high_protein = any(k in fuel_text for k in ["高蛋白", "蛋白每日 ≥", "蛋白增加"])
    if not high_protein:
        return conflicts

    # 看 labs 肌酐
    creatinine = getattr(twin.labs, "creatinine", None)
    if creatinine and creatinine > 110:  # μmol/L, 男性正常上限 ~106, 女性 ~98
        conflicts.append(Conflict(
            specialist_a="fuel_strategist",
            specialist_b="metabolic_specialist",
            severity="hard",
            description=(
                f"FuelStrategist 建议提高蛋白摄入, 但用户肌酐 {creatinine} μmol/L 偏高. "
                f"高蛋白可能加重肾脏负担."
            ),
            resolution_hint=(
                "建议: 蛋白摄入控制在 0.8 g/kg/天 (而非运动恢复的 1.6+), "
                "并复查肌酐 + eGFR + 尿微量白蛋白. 涉及肾功能的决策须先咨询执业医师."
            ),
        ))
    return conflicts


def _check_movement_vs_recovery(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """MovementCoach 加训 + RecoveryCoach 状态=rest → 冲突."""
    conflicts = []
    movement = _get_finding(findings, "movement_coach")
    recovery = _get_finding(findings, "recovery_coach")
    if not (movement and recovery):
        return conflicts

    rec_zone = (recovery.raw or {}).get("zone")
    mov_status = (movement.raw or {}).get("status")
    if rec_zone == "rest" and mov_status == "undertrained":
        conflicts.append(Conflict(
            specialist_a="movement_coach",
            specialist_b="recovery_coach",
            severity="soft",
            description=(
                f"MovementCoach 标记 undertrained 建议加训, 但 RecoveryCoach 评估 "
                f"readiness=rest. 短期建议遵循 RecoveryCoach 优先."
            ),
            resolution_hint=(
                "今日只做主动恢复 (zone 1, 30 分钟内). 等 readiness 回到 moderate "
                "再按 MovementCoach 计划加训."
            ),
        ))
    return conflicts


def _check_alcohol_directive(
    findings: List[SpecialistFinding], twin: HealthTwin, db,
) -> List[Conflict]:
    """如有 'lifestyle 戒酒' directive, 但 fuel finding 提到酒精 → 冲突."""
    if not db:
        return []
    conflicts = []
    try:
        from app.models.user_directive import UserDirective
        from datetime import datetime, timezone
        from sqlalchemy import or_
        now = datetime.now(timezone.utc)
        alcohol_directive = db.query(UserDirective).filter(
            UserDirective.user_id == twin.meta.user_id,
            UserDirective.status == "active",
            UserDirective.kind == "lifestyle",
            or_(UserDirective.expires_at.is_(None), UserDirective.expires_at > now),
            UserDirective.instruction.ilike("%戒酒%") | UserDirective.instruction.ilike("%limit alcohol%"),
        ).first()
        if not alcohol_directive:
            return []

        fuel = _get_finding(findings, "fuel_strategist")
        if fuel:
            fuel_text = (fuel.summary or "") + " ".join(
                str(f.get("text", "") or "") for f in fuel.findings
            )
            if "酒" in fuel_text and "戒" not in fuel_text and "禁" not in fuel_text:
                conflicts.append(Conflict(
                    specialist_a="fuel_strategist",
                    specialist_b="user_directive",
                    severity="hard",
                    description=(
                        f"用户已设硬性指令 '{alcohol_directive.instruction[:60]}', "
                        f"但 FuelStrategist 输出仍含酒精相关内容."
                    ),
                    resolution_hint=(
                        "FuelStrategist 应忽略酒精相关建议, 严格遵循戒酒 directive."
                    ),
                ))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[cross_review] 戒酒 directive 检查失败 (跳过): {e}")
    return conflicts


def _check_supplement_vs_medication(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """SafetyGuardian 已有 51 条 DSI 规则覆盖大部分. 这里只补一条:
    Fuel/任何 specialist 推荐补剂 + 用户在服强相互作用药 → 强提示."""
    # 占位: 留给未来扩展. SafetyGuardian 已经有 DSI 7 条规则在跑.
    return []


# ─────────────────────── 主入口 ───────────────────────


CHECKS = [
    _check_protein_vs_kidney,
    _check_movement_vs_recovery,
]


def detect_conflicts(
    findings: List[SpecialistFinding], twin: HealthTwin, db=None,
) -> List[Conflict]:
    """跑所有 conflict checker, 收集冲突."""
    conflicts: List[Conflict] = []
    for check in CHECKS:
        try:
            conflicts.extend(check(findings, twin) or [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[cross_review] {check.__name__} 失败 (跳过): {e}")
    # 单独跑 directive-aware checks (需要 db)
    if db:
        try:
            conflicts.extend(_check_alcohol_directive(findings, twin, db) or [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[cross_review] alcohol directive check 失败: {e}")
    return conflicts


def render_conflicts_for_prompt(conflicts: List[Conflict]) -> str:
    """把 conflicts 拼成 markdown 给 LLM 合成 prompt."""
    if not conflicts:
        return ""
    lines = ["## ⚠️ Specialist 之间检测到矛盾 — 你必须明示如何裁决"]
    for c in conflicts:
        sev = "🔴 hard" if c.severity == "hard" else "🟡 soft"
        lines.append(f"\n### {sev}: {c.specialist_a} vs {c.specialist_b}")
        lines.append(f"- 矛盾: {c.description}")
        lines.append(f"- 建议处理: {c.resolution_hint}")
    return "\n".join(lines)
