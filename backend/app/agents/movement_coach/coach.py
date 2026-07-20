"""
Movement Coach —— 训练负荷与今日训练处方。

关键概念：
- ACWR (Acute:Chronic Workload Ratio) —— 过载/欠训练的核心指标
    optimal: 0.8 - 1.3
    overload: > 1.5
    deconditioning: < 0.8
- 今日建议由两个信号叉乘决定：
    training_status (由 ACWR 决定)
    × readiness (由 Recovery Coach 决定，可选)

  — status=optimal × readiness=hard   → 高强度 OK
  — status=optimal × readiness=rest   → 改为主动恢复
  — status=overload × 任何 readiness  → 强制 deload

基因驱动提示：
- ACTN3 RR  → 力量/爆发优势
- ACTN3 XX  → 耐力优势
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.orchestrator.schema import Intent, ProposedCard, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


# ─────────────────────── 工具 ───────────────────────────


def _safe(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _training_status(acwr: Optional[float], workouts_this_week: Optional[int]) -> str:
    if acwr is None and not workouts_this_week:
        return "unknown"
    if acwr is None:
        return "building" if (workouts_this_week or 0) >= 3 else "undertrained"
    if acwr > 1.5:
        return "overload"
    if acwr >= 1.3:
        return "peaking"      # 接近峰值，可保持
    if acwr >= 0.8:
        return "optimal"
    if acwr >= 0.5:
        return "undertrained"
    return "detraining"


# Garmin 官方 training_status 枚举 → 我们的 decision matrix key
# Garmin 字符串: productive / maintaining / detraining / overreaching / peaking / recovery / unproductive
# Garmin 整数编码 (garminconnect SDK): 1=detraining 2=maintaining 3=productive 4=peaking
#                                    5=overreaching 6=unproductive 7=recovery 8=strained
# 采集器优先写字符串, 字符串缺失时存 str(int). 两种都接受.
_GARMIN_STATUS_MAP = {
    # 字符串名
    "productive": "optimal",
    "maintaining": "optimal",
    "peaking": "peaking",
    "overreaching": "overload",
    "unproductive": "overload",
    "recovery": "undertrained",
    "detraining": "detraining",
    "strained": "overload",
    "no_status": "unknown",
    # 整数编码 (存为 str) — 用户观测到有些账户拿不到 key
    "1": "detraining",
    "2": "optimal",       # maintaining
    "3": "optimal",       # productive
    "4": "peaking",
    "5": "overload",      # overreaching
    "6": "overload",      # unproductive
    "7": "undertrained",  # recovery
    "8": "overload",      # strained
    "0": "unknown",
}


def _resolve_training_status(twin) -> tuple[str, str]:
    """优先用 Garmin 官方 training_status, 否则用自算 ACWR 派生.

    Returns: (status, source) — source ∈ {"garmin", "computed"}

    冲突保护 (2026-05-12, G-W4 自评发现): Garmin 偶尔在用户高强度周仍标
    'recovery'/'detraining', 但 ACWR > 1.5 明确指向过载. 此时以数据为准,
    覆盖到 'overload', source 标 'computed' 让 UI 显示 "自算".
    避免 summary 出现 "负荷偏低（ACWR 2.38）" 这种自相矛盾。
    """
    b = twin.behavioral
    acwr = _safe(b.acute_chronic_ratio)
    garmin_status = getattr(b, "training_status", None)
    if garmin_status and garmin_status in _GARMIN_STATUS_MAP:
        mapped = _GARMIN_STATUS_MAP[garmin_status]
        if acwr is not None and acwr > 1.5 and mapped in ("undertrained", "detraining"):
            return "overload", "computed"
        return mapped, "garmin"
    return _training_status(acwr, b.workouts_this_week), "computed"


# 决策矩阵：training_status × readiness_zone → 今日强度
_INTENSITY_MATRIX = {
    ("optimal", "hard"):       ("high",     "高强度间歇或大重量力量；目标 RPE 7-9"),
    ("optimal", "moderate"):   ("moderate", "Z2-Z3 有氧 45-60 分钟，或中重量力量 RPE 6-7"),
    ("optimal", "light"):      ("low",      "Z1-Z2 轻有氧 30-40 分钟，避免高心率"),
    ("optimal", "rest"):       ("rest",     "今天跳过训练或做 15 分钟活动度流动"),

    ("peaking", "hard"):       ("high",     "可做 1 次质量训练，之后保持"),
    ("peaking", "moderate"):   ("moderate", "Z2 有氧为主，巩固当前能力"),
    ("peaking", "light"):      ("low",      "低强度恢复，不增负荷"),
    ("peaking", "rest"):       ("rest",     "主动恢复，避免再加负荷"),

    ("overload", "hard"):      ("low",      "强制降强度！过载窗口期，高风险受伤"),
    ("overload", "moderate"):  ("low",      "降到 Z1 有氧或停训 1-2 天"),
    ("overload", "light"):     ("rest",     "完全休息 2-3 天让 ACWR 回落"),
    ("overload", "rest"):      ("rest",     "彻底休息，补觉补水"),

    ("undertrained", "hard"):  ("moderate", "循序渐进加量，一次加 1 次有氧或 1 次力量"),
    ("undertrained", "moderate"): ("moderate", "Z2 有氧 40-50 分钟启动"),
    ("undertrained", "light"): ("low",      "先从 20-30 分钟快走/慢跑开始"),
    ("undertrained", "rest"):  ("rest",     "先处理恢复，明天再启动"),

    ("detraining", "hard"):    ("low",      "重新启动要缓慢，先 2 周低强度重建基础"),
    ("detraining", "moderate"):("low",      "20-30 分钟快走或动作练习"),
    ("detraining", "light"):   ("low",      "开始的是"),
    ("detraining", "rest"):    ("rest",     "先休息调整"),

    ("building", "hard"):      ("moderate", "保持当前节奏，可加质量训练"),
    ("building", "moderate"):  ("moderate", "Z2 有氧 40-50 分钟"),
    ("building", "light"):     ("low",      "低强度维持"),
    ("building", "rest"):      ("rest",     "恢复优先"),
}


def _today_intensity(status: str, readiness_zone: Optional[str]) -> tuple[str, str]:
    """返回 (intensity_code, guidance_text)。"""
    if status == "unknown":
        return ("unknown", "训练数据不足，建议先同步 Garmin 活动记录")
    zone = readiness_zone or "moderate"  # 默认假设中等恢复
    key = (status, zone)
    if key in _INTENSITY_MATRIX:
        return _INTENSITY_MATRIX[key]
    return ("moderate", "按当前状态中等强度安排")


# ─────────────────────── 基因提示 ────────────────────────


def _gene_bias(twin: HealthTwin) -> Optional[Dict[str, Any]]:
    all_variants = (
        (twin.genetic.drug_sensitivity or [])
        + (twin.genetic.risk_variants or [])
        + (twin.genetic.protective_variants or [])
        + (twin.genetic.exercise_variants or [])
    )
    by_gene: Dict[str, Dict[str, Any]] = {}
    for v in all_variants or []:
        name = (v.get("gene_name") or "").upper()
        if name:
            by_gene.setdefault(name, v)

    result: Dict[str, Any] = {}
    tips: List[str] = []

    actn3 = by_gene.get("ACTN3")
    if actn3:
        geno = (actn3.get("genotype") or "").upper()
        if "RR" in geno:
            result.update({"gene": "ACTN3 RR", "bias": "力量/爆发优势"})
            tips.append("侧重力量与短距离爆发训练")
        elif "XX" in geno:
            result.update({"gene": "ACTN3 XX", "bias": "耐力优势"})
            tips.append("增加长距离Z2比例，力量训练仍需做")
        elif "RX" in geno:
            result.update({"gene": "ACTN3 RX", "bias": "均衡型"})
            tips.append("力量与耐力都有潜力，按目标灵活调整")

    ace = by_gene.get("ACE")
    if ace:
        geno = (ace.get("genotype") or "").upper()
        if "II" in geno:
            tips.append("ACE II耐力型→适合马拉松/铁三/长距离骑行")
            if "bias" not in result:
                result.update({"gene": "ACE II", "bias": "耐力型"})
        elif "DD" in geno:
            tips.append("ACE DD力量型→适合短跑/举重/HIIT")
            if "bias" not in result:
                result.update({"gene": "ACE DD", "bias": "力量/爆发型"})

    col5a1 = by_gene.get("COL5A1")
    if col5a1 and (col5a1.get("risk_level") or "").lower() in ("medium", "high"):
        tips.append("COL5A1变异→肌腱韧带损伤风险偏高→充分热身、逐步加量、重视离心训练")

    nos3 = by_gene.get("NOS3")
    if nos3 and (nos3.get("risk_level") or "").lower() in ("medium", "high"):
        tips.append("NOS3变异→血管扩张能力偏弱→甜菜根汁(硝酸盐)可改善运动时氧输送")

    if not result:
        return None

    result["tip"] = "；".join(tips) + "。"
    return result


# ─────────────────────── Specialist ────────────────────────


class MovementCoachSpecialist:
    name = "movement_coach"
    category = "movement"

    TRIGGER_KEYWORDS = {
        "训练", "运动", "跑步", "跑", "健身", "锻炼", "力量",
        "有氧", "间歇", "配速", "心率", "阈值",
        "今天练", "今天能练", "今天跑",
        "workout", "training", "run", "lift", "exercise",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "movement" in intent.categories:
            return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 兜底：dashboard 场景下只要有训练负荷数据就参与
        if "general" in intent.categories and twin.behavioral.training_load_7d is not None:
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            b = twin.behavioral
            p = twin.physiological

            acwr = _safe(b.acute_chronic_ratio)
            status, status_source = _resolve_training_status(twin)

            # readiness 可以从 context 或从 Recovery Coach 的 finding 里取
            readiness_zone = context.get("readiness_zone")

            intensity_code, guidance = _today_intensity(status, readiness_zone)
            acute = getattr(twin, "acute", None)
            acute_rest = bool(getattr(acute, "should_rest_from_training", False))
            acute_guardrail = getattr(acute, "training_guardrail", None)
            if acute_rest:
                intensity_code = "rest"
                guidance = acute_guardrail or "当前有急性不适/生病状态，今天不要求完成运动目标，优先休息。"

            findings: List[Dict[str, Any]] = [
                {
                    "type": "training_status",
                    "status": status,
                    "source": status_source,  # garmin / computed — 用户 UI 可展示 "Garmin 官方"
                    "acwr": acwr,
                    "garmin_load_ratio": _safe(getattr(b, "load_ratio", None)),
                    "garmin_acute_load": _safe(getattr(b, "acute_load", None)),
                    "training_load_7d": _safe(b.training_load_7d),
                    "workouts_this_week": b.workouts_this_week,
                    "garmin_feedback": getattr(b, "training_status_feedback", None),
                },
                {
                    "type": "today_prescription",
                    "intensity": intensity_code,
                    "guidance": guidance,
                    "based_on_readiness": readiness_zone,
                    **({"reason": "acute_illness"} if acute_rest else {}),
                },
            ]

            # VO2max / RHR 快照
            if p.vo2max_running or p.resting_hr:
                findings.append({
                    "type": "fitness_snapshot",
                    "vo2max_running": p.vo2max_running,
                    "vo2max_cycling": p.vo2max_cycling,
                    "resting_hr": p.resting_hr,
                })

            # 基因提示
            gene = _gene_bias(twin)
            if gene:
                findings.append({"type": "gene_bias", **gene})

            # 本周调整
            adj = _week_adjustment(status, b.workouts_this_week or 0)
            if adj:
                findings.append({"type": "week_adjustment", "text": adj})

            # 近 7 天训练细节 (HR zones / 主观疲劳 / 训练效果)
            if b.recent_workouts:
                recent = b.recent_workouts[:5]
                findings.append({
                    "type": "recent_workout_detail",
                    "count": len(b.recent_workouts),
                    "workouts": [
                        {
                            "date": w.workout_date,
                            "type": w.workout_type,
                            "duration_min": w.duration_min,
                            "distance_km": w.distance_km,
                            "avg_hr": w.avg_hr,
                            "max_hr": w.max_hr,
                            "hr_zone_dominant": w.hr_zone_dominant,
                            "training_effect_aerobic": w.training_effect_aerobic,
                            "training_effect_anaerobic": w.training_effect_anaerobic,
                            "perceived_exertion": w.perceived_exertion,
                            "feeling": w.feeling,
                        }
                        for w in recent
                    ],
                    # 聚合: 近 7 天主观疲劳均值, 累计 HR Z4+Z5 分钟
                    "avg_perceived_exertion": (
                        round(sum(w.perceived_exertion for w in b.recent_workouts
                                   if w.perceived_exertion) /
                              max(1, sum(1 for w in b.recent_workouts if w.perceived_exertion)), 1)
                        if any(w.perceived_exertion for w in b.recent_workouts) else None
                    ),
                    "high_intensity_minutes_7d": round(sum(
                        (w.hr_zone_minutes or {}).get("z4", 0) +
                        (w.hr_zone_minutes or {}).get("z5", 0)
                        for w in b.recent_workouts
                    ), 1),
                })

            # 概括
            status_zh = {
                "optimal": "负荷最佳区",
                "peaking": "接近峰值",
                "overload": "过载风险",
                "undertrained": "负荷偏低",
                "detraining": "脱训阶段",
                "building": "负荷构建中",
                "unknown": "负荷未知",
            }.get(status, status)

            if acwr is not None:
                summary = f"训练 {status_zh}（ACWR {acwr:.2f}）· 今日建议 {intensity_code}"
            else:
                summary = f"训练 {status_zh} · 今日建议 {intensity_code}"

            # 信任循环: undertrained / overload 各产一张可验证假设
            proposed_cards: List[ProposedCard] = []
            wpw = b.workouts_this_week or 0
            if acute_rest:
                proposed_cards = []
            elif status == "undertrained" and wpw < 3:
                target_count = max(3, wpw + 2)
                proposed_cards.append(ProposedCard(
                    title=f"未来 7 天加训：每周训练 {wpw} → {target_count} 次",
                    content=(
                        f"## 7 天训练量提升实验\n\n"
                        f"**起点**: 本周训练 {wpw} 次\n"
                        f"**目标**: 7 天后周训练 ≥ {target_count} 次\n\n"
                        f"### 行动\n"
                        f"- 周一/三/五: 30-40 分钟 zone 2 有氧 (快走/慢跑/骑车)\n"
                        f"- 周末加 1 次力量 (深蹲/卧推/划船 各 3 组 × 8-12)\n"
                        f"- 单次训练心率不超过 HRmax × 0.7 (避免一上来过载)\n\n"
                        f"7 天后系统检查 workouts_this_week 数据自动评分。"
                    ),
                    metric_key="custom",
                    baseline_value=str(wpw),
                    target_value=f">={target_count}",
                    verification_days=7,
                    card_type="plan",
                    priority=12,
                ))
            elif status == "overload" and acwr:
                # ACWR > 1.5 — 强制 deload
                proposed_cards.append(ProposedCard(
                    title=f"7 天 deload：ACWR {acwr:.1f} → ≤ 1.0",
                    content=(
                        f"## 7 天主动减量恢复\n\n"
                        f"**起点**: ACWR {acwr:.1f} (overload)\n"
                        f"**目标**: 7 天后 ACWR ≤ 1.0\n\n"
                        f"### 行动\n"
                        f"- 本周训练负荷降到上周的 60% (时长或强度)\n"
                        f"- 高强度 (zone 4-5) 0 次，全部转 zone 2\n"
                        f"- 增加睡眠 30-60 min/天\n"
                        f"- 力量训练改为技术性 (轻重量, 高质量动作)\n\n"
                        f"过载是受伤窗口，强制 deload 比硬训更省时间。"
                    ),
                    metric_key="custom",
                    baseline_value=f"{acwr:.2f}",
                    target_value="<=1.0",
                    verification_days=7,
                    card_type="plan",
                    priority=20,  # overload 高优先级
                ))
            # Movement forecast 暂未发出: outcome_grader._fetch_metric 不支持 ACWR /
            # workouts_this_week, 押了也评不出. 等 _fetch_metric 加 movement metric
            # 支持后, 再恢复 status=='optimal' 时的 forecast 推送.

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "status": status,
                    "acwr": acwr,
                    "intensity": intensity_code,
                    "readiness_used": readiness_zone,
                    "acute_rest": acute_rest,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
                proposed_cards=proposed_cards,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[movement_coach] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"训练评估失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )


def _week_adjustment(status: str, workouts_this_week: int) -> Optional[str]:
    if status == "overload":
        return "本周剩余训练全部降强度；下周 deload 一次，让 ACWR 回到 0.8-1.3。"
    if status == "undertrained" and workouts_this_week < 3:
        return "下周目标：3 次 Z2 有氧 + 2 次力量，缓慢提升 ACWR。"
    if status == "detraining":
        return "前 2 周重建基础，不追求强度；只看训练次数和总时长。"
    if status == "peaking":
        return "保持当前频率，避免再加量；比赛前 1 周进入 taper。"
    return None
