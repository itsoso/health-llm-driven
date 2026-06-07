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


def _check_high_intensity_vs_uncontrolled_bp(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """MovementCoach 建议 hard intensity + 血压 stage2+ (≥140/90) → 硬冲突."""
    conflicts = []
    movement = _get_finding(findings, "movement_coach")
    if not movement:
        return conflicts
    intensity = (movement.raw or {}).get("intensity")
    if intensity not in {"hard", "moderate"}:
        return conflicts
    sbp = twin.labs.blood_pressure_systolic
    dbp = twin.labs.blood_pressure_diastolic
    if (sbp and sbp >= 140) or (dbp and dbp >= 90):
        conflicts.append(Conflict(
            specialist_a="movement_coach",
            specialist_b="hypertension_specialist",
            severity="hard",
            description=(
                f"MovementCoach 建议 {intensity} 训练强度, 但血压 {sbp}/{dbp} mmHg "
                f"处于 stage 2+ 未控制. 高强度运动可急性升压至危险区."
            ),
            resolution_hint=(
                "今日改为 zone 1-2 低强度 30 分钟内. 血压稳定回 <130/80 且按医嘱规范服药后再加强度."
            ),
        ))
    return conflicts


def _check_protein_vs_gout(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """FuelStrategist 推高蛋白 + 尿酸偏高 → 痛风风险."""
    conflicts = []
    fuel = _get_finding(findings, "fuel_strategist")
    if not fuel:
        return conflicts
    fuel_text = (fuel.summary or "") + " ".join(
        str(f.get("text", "") or "") for f in fuel.findings
    )
    if not any(k in fuel_text for k in ["高蛋白", "蛋白每日 ≥", "蛋白增加", "红肉", "动物蛋白"]):
        return conflicts
    ua = twin.labs.uric_acid
    # 男性 > 420 μmol/L, 保守用 420 作统一阈值（更严格需结合性别）
    if ua and ua > 420:
        conflicts.append(Conflict(
            specialist_a="fuel_strategist",
            specialist_b="metabolic_specialist",
            severity="hard",
            description=(
                f"FuelStrategist 建议高蛋白/红肉类摄入, 但尿酸 {ua} μmol/L 偏高, "
                f"红肉/海鲜/内脏 prurine 易诱发痛风急性发作."
            ),
            resolution_hint=(
                "蛋白源优先选择低嘌呤（乳清/鸡蛋/鱼肉淡水鱼/豆腐）, "
                "避免动物内脏/贝类/浓肉汤. 建议复查尿酸, 涉及降尿酸药需咨询执业医师."
            ),
        ))
    return conflicts


def _check_caffeine_vs_poor_sleep(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """Fuel 推咖啡因 + 睡眠 7d 差 → 放大睡眠问题."""
    conflicts = []
    fuel = _get_finding(findings, "fuel_strategist")
    if not fuel:
        return conflicts
    fuel_text = (fuel.summary or "") + " ".join(
        str(f.get("text", "") or "") for f in fuel.findings
    )
    if not any(k in fuel_text for k in ["咖啡", "caffeine", "浓茶"]):
        return conflicts
    sleep_7d = twin.mental.sleep_quality_7d_avg
    sleep_latest = twin.physiological.sleep_score_latest
    if (sleep_7d is not None and sleep_7d < 60) or (sleep_latest is not None and sleep_latest < 60):
        conflicts.append(Conflict(
            specialist_a="fuel_strategist",
            specialist_b="recovery_coach",
            severity="soft",
            description=(
                f"FuelStrategist 建议含咖啡因饮品, 但近期睡眠评分偏低 "
                f"(7d 均值={sleep_7d}, 最新={sleep_latest}). 咖啡因半衰期 5-6h, 下午后摄入会加剧."
            ),
            resolution_hint=(
                "若确需咖啡因, 限制在午前 (< 14:00) + 总量 < 200 mg. "
                "已有睡眠问题时优先改善睡眠卫生而非依赖咖啡因提神."
            ),
        ))
    return conflicts


def _check_supplement_bleeding_vs_anticoagulant(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """补剂推鱼油/银杏/大蒜/维E + 用户在服抗凝药 → 出血风险."""
    conflicts = []
    # 收集所有 finding 文本
    all_text = ""
    for f in findings:
        all_text += " " + (f.summary or "")
        for item in (f.findings or []):
            all_text += " " + str(item.get("text", "") or "")
        for pc in (f.proposed_cards or []):
            all_text += " " + (pc.title or "") + " " + (pc.content or "")

    bleed_supplements = [k for k in ["鱼油", "ω-3", "omega-3", "银杏", "ginkgo",
                                      "大蒜", "garlic", "维生素E", "vitamin E", "姜黄", "turmeric"]
                         if k.lower() in all_text.lower()]
    if not bleed_supplements:
        return conflicts

    # 检查 med list
    anticoag_names = ["华法林", "warfarin", "阿司匹林", "aspirin", "氯吡格雷", "clopidogrel",
                      "利伐沙班", "rivaroxaban", "阿哌沙班", "apixaban", "达比加群", "dabigatran",
                      "依度沙班", "edoxaban"]
    user_meds = twin.medication.active_meds or []
    matched_anticoag = None
    for med in user_meds:
        name = (med.get("name") or med.get("drug_name") or "").lower()
        for a in anticoag_names:
            if a.lower() in name:
                matched_anticoag = name
                break
        if matched_anticoag:
            break

    if matched_anticoag:
        conflicts.append(Conflict(
            specialist_a="supplement_advisor",
            specialist_b="safety_guardian",
            severity="hard",
            description=(
                f"建议中包含 {', '.join(bleed_supplements)} 等具有抗血小板/抗凝活性的成分, "
                f"但用户正在服用抗凝药 {matched_anticoag}. 联用显著增加出血风险."
            ),
            resolution_hint=(
                "移除以上补剂建议. 任何补剂与抗凝药的联用需执业医师评估 INR / 出血风险后决策."
            ),
        ))
    return conflicts


def _check_rhinitis_dose_up_vs_adherence(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """RhinitisSpecialist 建议加量 + 用药依从度 < 50% → 先解决依从性再加量."""
    conflicts = []
    rhinitis = _get_finding(findings, "rhinitis_specialist")
    if not rhinitis:
        return conflicts
    rhin_text = (rhinitis.summary or "") + " ".join(
        str(f.get("text", "") or "") for f in rhinitis.findings
    )
    if not any(k in rhin_text for k in ["加量", "增加剂量", "加一喷", "升级治疗", "step up"]):
        return conflicts
    adherence = twin.medication.adherence_7d_pct
    if adherence is not None and adherence < 50:
        conflicts.append(Conflict(
            specialist_a="rhinitis_specialist",
            specialist_b="safety_guardian",
            severity="soft",
            description=(
                f"RhinitisSpecialist 建议上调鼻炎用药剂量, 但近 7 天用药依从度仅 {adherence:.0f}%. "
                f"剂量问题之前应先解决\"是否按时用\"的问题."
            ),
            resolution_hint=(
                "先把现有剂量按时用满 7 天（用提醒/固定使用情景锚点）, 再评估是否加量. "
                "依从度不足的加量是在\"用更大剂量治 50% 的遵循\"."
            ),
        ))
    return conflicts


def _check_high_intensity_vs_sleep_debt(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """MovementCoach 建议 hard + 睡眠时长短/质量差 → 恢复不足, 伤病风险."""
    conflicts = []
    movement = _get_finding(findings, "movement_coach")
    if not movement:
        return conflicts
    intensity = (movement.raw or {}).get("intensity")
    if intensity != "hard":
        return conflicts
    sleep_latest = twin.physiological.sleep_duration_h_latest
    deep_14d = twin.physiological.sleep_deep_h_avg_14d
    conditions = []
    if sleep_latest is not None and sleep_latest < 6.0:
        conditions.append(f"昨夜仅睡 {sleep_latest:.1f}h")
    if deep_14d is not None and deep_14d < 0.8:
        conditions.append(f"14d 深睡均值仅 {deep_14d:.1f}h")
    if not conditions:
        return conflicts
    conflicts.append(Conflict(
        specialist_a="movement_coach",
        specialist_b="recovery_coach",
        severity="soft",
        description=(
            f"MovementCoach 建议 hard 强度, 但 {', '.join(conditions)}. "
            f"恢复不足状态硬练会累积伤病和过度训练风险."
        ),
        resolution_hint=(
            "今日降级至 zone 2 / moderate, 优先补足睡眠. 连续 2 夜 ≥ 7h 后再考虑 hard 训练."
        ),
    ))
    return conflicts


def _check_stopped_med_directive(
    findings: List[SpecialistFinding], twin: HealthTwin, db,
) -> List[Conflict]:
    """user_directive 明确"停用 X 药", 但 specialist 仍引用该药 → 矛盾."""
    if not db:
        return []
    conflicts = []
    try:
        from app.models.user_directive import UserDirective
        from datetime import datetime, timezone
        from sqlalchemy import or_
        now = datetime.now(timezone.utc)
        stopped_directives = db.query(UserDirective).filter(
            UserDirective.user_id == twin.meta.user_id,
            UserDirective.status == "active",
            UserDirective.kind == "medication_change",
            or_(UserDirective.expires_at.is_(None), UserDirective.expires_at > now),
            UserDirective.instruction.op("~*")(r"停(用|服|药)|暂停|discontinue|stop"),
        ).all()
        if not stopped_directives:
            return []

        # 拿到 directive 涉及的药名 (structured field 或 从 instruction 中提)
        stopped_names = []
        for d in stopped_directives:
            if getattr(d, "medication_name", None):
                stopped_names.append(d.medication_name)
            # 也从 instruction 里抓中文药名（粗略）
            stopped_names.append(d.instruction[:80])

        # 扫所有 finding 文本
        for f in findings:
            if f.specialist_name == "user_directive":
                continue
            f_text = (f.summary or "") + " ".join(
                str(item.get("text", "") or "") for item in f.findings
            )
            for name in stopped_names:
                if not name or len(name) < 2:
                    continue
                # 取药名头部 3-4 字符做 loose 匹配, 避免 '停用 X' instruction 字符串误匹配自己
                key = name[:4]
                if key in f_text and "停" not in f_text:
                    conflicts.append(Conflict(
                        specialist_a=f.specialist_name,
                        specialist_b="user_directive",
                        severity="hard",
                        description=(
                            f"用户已设 directive 停用某药 (\"{name[:40]}...\"), "
                            f"但 {f.specialist_name} 输出仍引用该药名."
                        ),
                        resolution_hint=(
                            f"{f.specialist_name} 应忽略已停用药物, 重新评估分析结论."
                        ),
                    ))
                    break  # 同一个 finding 匹到一个就够了
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[cross_review] stopped med directive check failed: {e}")
    return conflicts


def _check_longevity_intensify_vs_low_readiness(
    findings: List[SpecialistFinding], twin: HealthTwin,
) -> List[Conflict]:
    """LongevitySpecialist 提 12 周抗衰 N-of-1(含加量协议)+ RecoveryCoach readiness=rest
    → 冲突:别在低恢复期硬启动强干预周期。"""
    conflicts = []
    longevity = _get_finding(findings, "longevity")
    recovery = _get_finding(findings, "recovery_coach")
    if not (longevity and recovery):
        return conflicts
    # 提了 N-of-1 卡 = 要启动 12 周强干预周期
    if not getattr(longevity, "proposed_cards", None):
        return conflicts
    if (recovery.raw or {}).get("zone") == "rest":
        conflicts.append(Conflict(
            specialist_a="longevity",
            specialist_b="recovery_coach",
            severity="soft",
            description=(
                "LongevitySpecialist 建议启动 12 周抗衰 N-of-1(含运动/强度加量), "
                "但 RecoveryCoach 评估 readiness=rest. 低恢复期硬启动强周期适得其反."
            ),
            resolution_hint=(
                "先做 3-5 天主动恢复(睡眠/低强度), readiness 回到 moderate 再启动 "
                "12 周计划; 计划里的营养/睡眠支柱可以先开始, 运动支柱缓启."
            ),
        ))
    return conflicts


# ─────────────────────── 主入口 ───────────────────────


CHECKS = [
    _check_protein_vs_kidney,
    _check_movement_vs_recovery,
    _check_high_intensity_vs_uncontrolled_bp,
    _check_protein_vs_gout,
    _check_caffeine_vs_poor_sleep,
    _check_supplement_bleeding_vs_anticoagulant,
    _check_rhinitis_dose_up_vs_adherence,
    _check_high_intensity_vs_sleep_debt,
    _check_longevity_intensify_vs_low_readiness,
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
        for db_check in (_check_alcohol_directive, _check_stopped_med_directive):
            try:
                conflicts.extend(db_check(findings, twin, db) or [])
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[cross_review] {db_check.__name__} 失败: {e}")
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
