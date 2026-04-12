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

from app.orchestrator.schema import Intent, SpecialistFinding
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


def _gene_bias(twin: HealthTwin) -> Optional[Dict[str, str]]:
    for pool in (
        twin.genetic.drug_sensitivity,
        twin.genetic.risk_variants,
        twin.genetic.protective_variants,
    ):
        for v in pool or []:
            name = (v.get("gene_name") or "").upper()
            if name == "ACTN3":
                geno = (v.get("genotype") or "").upper()
                if "RR" in geno:
                    return {
                        "gene": "ACTN3 RR",
                        "bias": "力量/爆发优势",
                        "tip": "训练侧重力量与短距离爆发；马拉松等极限耐力相对吃亏，但不是不能做。",
                    }
                if "XX" in geno:
                    return {
                        "gene": "ACTN3 XX",
                        "bias": "耐力优势",
                        "tip": "训练可以增加长距离 Z2 比例；力量训练仍要做，防止肌少。",
                    }
                if "RX" in geno:
                    return {
                        "gene": "ACTN3 RX",
                        "bias": "均衡型",
                        "tip": "力量与耐力都有潜力，可根据目标灵活调整。",
                    }
    return None


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
            status = _training_status(acwr, b.workouts_this_week)

            # readiness 可以从 context 或从 Recovery Coach 的 finding 里取
            readiness_zone = context.get("readiness_zone")

            intensity_code, guidance = _today_intensity(status, readiness_zone)

            findings: List[Dict[str, Any]] = [
                {
                    "type": "training_status",
                    "status": status,
                    "acwr": acwr,
                    "training_load_7d": _safe(b.training_load_7d),
                    "workouts_this_week": b.workouts_this_week,
                },
                {
                    "type": "today_prescription",
                    "intensity": intensity_code,
                    "guidance": guidance,
                    "based_on_readiness": readiness_zone,
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
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
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
