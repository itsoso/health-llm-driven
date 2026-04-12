"""
Recovery Coach —— 恢复评分与行动建议。

Readiness score 算法（参考 WHOOP / Garmin Body Battery / HRV4Training 的加权组合）:
  0-100 分，60 以上可进行正常训练，85 以上可做高强度。

  组件权重：
    HRV 偏离   35%  （今日 HRV vs 7 日均值的相对差）
    睡眠质量   25%  （Garmin sleep score / 100 × 权重）
    睡眠时长   15%  （相对 7h 的比例，上限 1.15）
    Body Battery 15% （/100 × 权重）
    压力水平    10%  （反向：(100 - stress) / 100 × 权重）

  ACWR 惩罚：
    acwr > 1.5 扣 15；> 1.3 扣 8；< 0.5 不扣（恢复态）

缺数据时：该组件权重重新分摊到有数据的组件上，避免低估。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.orchestrator.schema import Intent, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


# ─────────────────────── 核心算法 ────────────────────────


@dataclass
class ReadinessBreakdown:
    score: int
    components: Dict[str, float]      # 每个组件的归一化得分 (0..1)
    weights_used: Dict[str, float]    # 实际使用的权重
    penalty: float                    # ACWR 惩罚
    missing_components: List[str]     # 缺数据的组件
    zone: str                         # rest / light / moderate / hard


_DEFAULT_WEIGHTS = {
    "hrv": 0.35,
    "sleep_quality": 0.25,
    "sleep_duration": 0.15,
    "body_battery": 0.15,
    "stress": 0.10,
}


def _safe(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def compute_readiness(twin: HealthTwin) -> ReadinessBreakdown:
    """对 Twin 计算 readiness 分数与分解。"""
    p = twin.physiological
    b = twin.behavioral

    components: Dict[str, Optional[float]] = {}

    # HRV: 今日 vs 7d 均值（±30% 归一化到 0.3..1.0）
    hrv_latest = _safe(p.hrv_latest)
    hrv_baseline = _safe(p.hrv_7d_avg)
    if hrv_latest is not None and hrv_baseline and hrv_baseline > 0:
        ratio = hrv_latest / hrv_baseline
        # ratio 1.0 → 0.85; 1.1 → 1.0; 0.85 → 0.5; 0.7 → 0.3
        components["hrv"] = _clip(0.85 + (ratio - 1.0) * 1.5)
    elif hrv_latest is not None:
        # 没有 baseline，做绝对值判断（>60ms 优秀）
        components["hrv"] = _clip((hrv_latest - 20) / 60)
    else:
        components["hrv"] = None

    # 睡眠质量
    sleep_score = _safe(p.sleep_score_latest)
    components["sleep_quality"] = sleep_score / 100.0 if sleep_score is not None else None

    # 睡眠时长（7h = 1.0，5h = 0.4，9h = 1.1）
    sleep_h = _safe(p.sleep_duration_h_latest)
    if sleep_h is not None:
        components["sleep_duration"] = _clip((sleep_h - 4.0) / 3.5, 0.0, 1.15)
    else:
        components["sleep_duration"] = None

    # Body battery
    bb = _safe(p.body_battery_current)
    components["body_battery"] = bb / 100.0 if bb is not None else None

    # 压力（反向）
    stress = _safe(p.stress_level_current)
    components["stress"] = (100.0 - stress) / 100.0 if stress is not None else None

    # 权重再分配：缺数据的组件把权重分给剩下的
    used_weights: Dict[str, float] = {}
    missing: List[str] = []
    available_total = 0.0
    for name, weight in _DEFAULT_WEIGHTS.items():
        if components.get(name) is None:
            missing.append(name)
        else:
            available_total += weight

    if available_total <= 0:
        return ReadinessBreakdown(
            score=0,
            components={},
            weights_used={},
            penalty=0.0,
            missing_components=list(_DEFAULT_WEIGHTS.keys()),
            zone="unknown",
        )

    score_raw = 0.0
    for name, weight in _DEFAULT_WEIGHTS.items():
        val = components.get(name)
        if val is None:
            continue
        used_weights[name] = weight / available_total
        score_raw += val * used_weights[name]

    # 0..1 → 0..100
    score = score_raw * 100.0

    # ACWR 惩罚
    acwr = _safe(b.acute_chronic_ratio)
    penalty = 0.0
    if acwr is not None:
        if acwr > 1.5:
            penalty = 15.0
        elif acwr > 1.3:
            penalty = 8.0
    score_final = _clip(score - penalty, 0.0, 100.0)

    zone = _readiness_zone(score_final, missing)

    return ReadinessBreakdown(
        score=int(round(score_final)),
        components={k: round(v, 3) for k, v in components.items() if v is not None},
        weights_used={k: round(v, 3) for k, v in used_weights.items()},
        penalty=penalty,
        missing_components=missing,
        zone=zone,
    )


def _readiness_zone(score: float, missing: List[str]) -> str:
    # 数据严重缺失时保守
    if len(missing) >= 4:
        return "unknown"
    if score >= 85:
        return "hard"        # 可高强度
    if score >= 70:
        return "moderate"    # 可中等强度
    if score >= 55:
        return "light"       # 建议低强度/Z2
    return "rest"            # 建议完全恢复


# ─────────────────────── 建议生成 ────────────────────────


def _build_actions(breakdown: ReadinessBreakdown, twin: HealthTwin) -> List[str]:
    actions: List[str] = []
    zone = breakdown.zone

    # 1. 今日训练建议
    if zone == "hard":
        actions.append("今天身体状态很好，可以进行高强度训练（阈值跑/间歇/力量大重量）。")
    elif zone == "moderate":
        actions.append("今天适合中等强度有氧（Z2 慢跑 30-50 分钟）或中重量力量训练。")
    elif zone == "light":
        actions.append("今天建议低强度活动（Z1 快走、瑜伽、流动训练），避免大重量和高心率间歇。")
    elif zone == "rest":
        actions.append("今天身体恢复不足，建议完全休息或仅做 15-20 分钟拉伸/散步。")
    else:
        actions.append("数据不足以评估恢复状态，建议先同步 Garmin 数据再判断。")

    # 2. 针对性修复建议
    comp = breakdown.components
    if comp.get("sleep_duration") is not None and comp["sleep_duration"] < 0.7:
        sleep_h = twin.physiological.sleep_duration_h_latest
        actions.append(
            f"昨晚睡眠仅 {sleep_h:.1f}h，今晚至少 7.5h；提前 30 分钟关屏幕、保持卧室 18-20°C。"
            if sleep_h
            else "昨晚睡眠不足，今晚优先保证 7.5h 以上。"
        )

    if comp.get("sleep_quality") is not None and comp["sleep_quality"] < 0.6:
        actions.append("睡眠质量偏低，今天避免下午后饮用咖啡因，晚餐提前至睡前 3h 以前。")

    if comp.get("hrv") is not None and comp["hrv"] < 0.5:
        actions.append("HRV 明显低于基线，说明自主神经偏交感亢进。建议做 5 分钟 4-7-8 呼吸或正念。")

    if comp.get("stress") is not None and comp["stress"] < 0.4:
        actions.append("压力值偏高，安排一次主动恢复：15 分钟散步或冷水洗脸。")

    if breakdown.penalty >= 10:
        actions.append(
            f"急慢性负荷比偏高（ACWR 扣分 {int(breakdown.penalty)}），"
            "未来 3-5 天显著降低强度，避免伤病风险。"
        )

    return actions[:4]  # 限制 4 条，避免信息过载


# ─────────────────────── Specialist 适配器 ────────────────────


class RecoveryCoachSpecialist:
    """Orchestrator 的 Recovery Coach 适配器。"""

    name = "recovery_coach"
    category = "recovery"

    TRIGGER_KEYWORDS = {
        "恢复", "累", "疲劳", "疲惫", "睡", "睡眠",
        "hrv", "休息", "精力", "状态", "readiness",
        "能不能训练", "今天能跑",
        "sleep", "recover", "fatigue", "rest", "tired",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        if "recovery" in intent.categories:
            return True
        q = (intent.raw_query or "").lower()
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # 兜底：如果 Twin 里生理数据齐全，让 coach 主动参与（user 的 dashboard 场景）
        p = twin.physiological
        if p.hrv_latest is not None and p.sleep_score_latest is not None:
            return "general" in intent.categories
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            breakdown = compute_readiness(twin)
            actions = _build_actions(breakdown, twin)

            findings: List[Dict[str, Any]] = [
                {
                    "type": "readiness_score",
                    "score": breakdown.score,
                    "zone": breakdown.zone,
                    "components": breakdown.components,
                    "weights_used": breakdown.weights_used,
                    "penalty": breakdown.penalty,
                    "missing": breakdown.missing_components,
                }
            ]
            for i, action in enumerate(actions, 1):
                findings.append({
                    "type": "action",
                    "order": i,
                    "text": action,
                })

            # 概括
            if breakdown.zone == "unknown":
                summary = "恢复状态未知（数据不足）"
            else:
                zone_zh = {
                    "hard": "状态极佳，可高强度训练",
                    "moderate": "状态良好，适合中等训练",
                    "light": "状态一般，建议低强度",
                    "rest": "恢复不足，建议休息",
                }[breakdown.zone]
                summary = f"Readiness {breakdown.score}/100 — {zone_zh}"

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "score": breakdown.score,
                    "zone": breakdown.zone,
                    "components": breakdown.components,
                    "penalty": breakdown.penalty,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[recovery_coach] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"恢复评估失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
