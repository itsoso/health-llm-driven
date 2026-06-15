"""今日训练决策引擎 (recovery_state_v2 / training_gate)。

回答一句话:**今天能不能练?练什么强度?** —— 多源恢复/训练决策引擎的 P0。

设计:核心是纯函数 `decide(...)`(不连库、不依赖 build_twin,可直接单测),把**已有**信号
映射成一盏灯 + 置信度 + 原因 + 一个动作。复用,不重造:
  - 恢复就绪度 zone/score → `recovery_coach.compute_readiness()`(已返回 0-100 + rest/light/moderate/hard)
  - 训练负荷 ACWR     → `twin.behavioral.acwr_zone`(under/optimal/risky,已采)
  - 急性病兜底        → `twin.acute`(has_active_illness / should_rest_from_training,已采)
  - 多设备一致性置信度 → `device_comparison_service.compare_sources()`(已算 per-metric agreement)

决策优先级:急性病 > 恢复债(zone) > 训练负荷(ACWR)。不做诊断、不开处方。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

# zone(恢复就绪度建议强度)→ 决策灯
_ZONE_TO_LIGHT = {"hard": "green", "moderate": "green", "light": "yellow", "rest": "red"}
_LIGHT_RANK = {"green": 2, "yellow": 1, "red": 0}

# 参与"设备一致性"的恢复相关指标(其余指标差异不影响训练决策置信度)
_AGREEMENT_METRICS = {"hrv", "resting_heart_rate", "total_sleep_duration", "spo2_avg"}


@dataclass
class TrainingDecision:
    light: str                       # green / yellow / red
    confidence: str                  # high / medium / low
    confidence_score: float          # 0..1
    readiness_score: Optional[int]
    zone: str                        # rest / light / moderate / hard
    source: str                      # garmin(官方 readiness) / computed(自算)
    reasons: List[str] = field(default_factory=list)
    next_action: str = ""
    agreement_index: Optional[float] = None
    missing_signals: List[str] = field(default_factory=list)


def _cap(light: str, ceiling: str) -> str:
    """把 light 封顶到 ceiling(取更保守的那个)。"""
    return light if _LIGHT_RANK[light] <= _LIGHT_RANK[ceiling] else ceiling


def _confidence(source: str, agreement_index: Optional[float], n_missing: int) -> Tuple[float, str]:
    """置信度:Garmin 官方 readiness 更全面 → 基线更高;多设备一致 → 拉高;缺信号 → 拉低。"""
    base = 0.7 if source == "garmin" else 0.5
    if agreement_index is not None:
        base = 0.5 * base + 0.5 * agreement_index  # 三设备一致性各占一半
    base -= 0.08 * n_missing
    base = max(0.0, min(1.0, base))
    label = "high" if base >= 0.75 else "medium" if base >= 0.5 else "low"
    return round(base, 3), label


def _next_action(light: str) -> str:
    if light == "red":
        return "今天恢复/休息,暂停高强度;优先睡眠与轻活动"
    if light == "yellow":
        return "降一级:优先 Zone 2 / 技术 / 轻力量,避免 VO2max"
    return "可按计划训练"


def decide(readiness: Any, acute: Any, behavioral: Any,
           agreement_index: Optional[float] = None) -> TrainingDecision:
    """纯函数:把恢复就绪度 + 急性病 + ACWR + 设备一致性 → 一盏训练决策灯。

    入参用 duck typing(只读属性),便于单测直接构造轻量对象。
    """
    zone = getattr(readiness, "zone", None) or "moderate"
    score = getattr(readiness, "score", None)
    source = getattr(readiness, "source", "computed") or "computed"
    missing = list(getattr(readiness, "missing_components", []) or [])
    reasons: List[str] = []

    light = _ZONE_TO_LIGHT.get(zone, "yellow")
    if score is not None:
        reasons.append(f"恢复就绪度 {score}/100(建议强度 {zone})")

    # 1) 急性病兜底 → red(最高优先)
    if getattr(acute, "should_rest_from_training", False) or getattr(acute, "has_active_illness", False):
        light = "red"
        names = (getattr(acute, "illness_names", None)
                 or getattr(acute, "recent_symptoms", None) or [])
        tail = f"({', '.join(names[:3])})" if names else ""
        reasons.append(f"检测到急性病/不适,训练应休息{tail}")

    # 2) ACWR 过载 → 封顶到黄(即使恢复就绪度是绿)
    acwr_zone = getattr(behavioral, "acwr_zone", None)
    if acwr_zone == "risky":
        capped = _cap(light, "yellow")
        if capped != light:
            reasons.append("急性训练负荷偏高(ACWR risky),高强度降级")
        light = capped
    elif acwr_zone == "under":
        reasons.append("训练负荷偏低(ACWR under),有余量")

    conf_score, conf_label = _confidence(source, agreement_index, len(missing))
    if agreement_index is not None:
        reasons.append(f"多设备一致性 {agreement_index:.0%}")
    if missing:
        reasons.append(f"缺 {len(missing)} 项信号:{', '.join(missing)}")

    return TrainingDecision(
        light=light,
        confidence=conf_label,
        confidence_score=conf_score,
        readiness_score=score,
        zone=zone,
        source=source,
        reasons=reasons,
        next_action=_next_action(light),
        agreement_index=agreement_index,
        missing_signals=missing,
    )


def device_agreement_index(db: Session, user_id: int, days: int = 7
                           ) -> Tuple[Optional[float], Dict[str, Any]]:
    """聚合 device_comparison 的 per-metric agreement → 单一恢复相关一致性指数。

    复用 `device_comparison_service.compare_sources`(已算 1−极差/均值)。
    单设备用户(<2 源)→ (None, ...),决策置信度退回只看 readiness source。
    """
    from app.services.device_comparison_service import device_comparison

    cmp = device_comparison(db, user_id, days=days)
    comps = [
        c for c in (cmp.get("comparisons") or [])
        if c.get("metric") in _AGREEMENT_METRICS and c.get("agreement") is not None
    ]
    detail: Dict[str, Any] = {"sources": cmp.get("sources", []), "by_metric": {}}
    if not comps:
        return None, detail
    by_metric = {c["metric"]: c["agreement"] for c in comps}
    detail["by_metric"] = by_metric
    idx = round(sum(by_metric.values()) / len(by_metric), 3)
    return idx, detail


def training_decision(db: Session, user_id: int) -> Dict[str, Any]:
    """端点组装:build_twin → compute_readiness → 设备一致性 → decide。返回 JSON。"""
    from app.agents.recovery_coach import compute_readiness
    from app.twin.builder import build_twin

    twin = build_twin(db, user_id, use_cache=True)
    rb = compute_readiness(twin)
    idx, agree_detail = device_agreement_index(db, user_id)
    decision = decide(rb, twin.acute, twin.behavioral, idx)

    out = asdict(decision)
    out["agreement_detail"] = agree_detail
    return out
