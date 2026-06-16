"""Leverage ActionRanker v0.

Pure scoring layer for Health Agenda items. It does not write database rows and
does not replace SafetyGuardian; it only annotates candidate actions with the
minimum metadata needed by wrist/mobile surfaces: score, short rationale,
priority tier, safety status, and a verification window.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


_CONFIDENCE_WEIGHT = {"low": 0.6, "medium": 0.8, "high": 1.0}
_TIER_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}

_DEFAULT_PROFILE: Dict[str, Any] = {
    "upstreamness": 3,
    "actionability": 3,
    "frequency": 3,
    "verifiability": 3,
    "confidence": "medium",
    "friction": 3,
    "priority_tier": "P2",
    "verification_window_days": 14,
    "rationale_short": "可执行健康动作, 完成后进入后续复盘",
    "safety_status": "allowed",
}


_KIND_PROFILES: Dict[str, Dict[str, Any]] = {
    "medication": {
        "upstreamness": 4,
        "actionability": 5,
        "frequency": 5,
        "verifiability": 4,
        "confidence": "high",
        "friction": 1,
        "priority_tier": "P1",
        "verification_window_days": 28,
        "rationale_short": "高频依从动作, 可在4周内验证完成率和目标指标",
    },
    "supplement": {
        "upstreamness": 4,
        "actionability": 5,
        "frequency": 5,
        "verifiability": 4,
        "confidence": "medium",
        "friction": 1,
        "priority_tier": "P1",
        "verification_window_days": 28,
        "rationale_short": "补剂依从动作, 先验证完成率再谈效果",
    },
    "diet": {
        "upstreamness": 5,
        "actionability": 4,
        "frequency": 5,
        "verifiability": 4,
        "confidence": "medium",
        "friction": 2,
        "priority_tier": "P2",
        "verification_window_days": 28,
        "rationale_short": "饮食相关上游动作, 可用体重/腰围/代谢指标复盘",
    },
    "hydration": {
        "upstreamness": 3,
        "actionability": 5,
        "frequency": 5,
        "verifiability": 2,
        "confidence": "medium",
        "friction": 1,
        "priority_tier": "P2",
        "verification_window_days": 7,
        "rationale_short": "低摩擦高频动作, 先保证当天执行",
    },
    "exercise": {
        "upstreamness": 5,
        "actionability": 4,
        "frequency": 4,
        "verifiability": 4,
        "confidence": "medium",
        "friction": 2,
        "priority_tier": "P2",
        "verification_window_days": 7,
        "rationale_short": "训练强度可直接调整, 可用RPE/HRV/RHR短周期验证",
    },
    "training": {
        "upstreamness": 5,
        "actionability": 4,
        "frequency": 4,
        "verifiability": 4,
        "confidence": "medium",
        "friction": 2,
        "priority_tier": "P2",
        "verification_window_days": 7,
        "rationale_short": "训练决策影响恢复和负荷, 可用RPE/HRV/RHR复盘",
    },
    "checkup": {
        "upstreamness": 4,
        "actionability": 4,
        "frequency": 1,
        "verifiability": 5,
        "confidence": "high",
        "friction": 3,
        "priority_tier": "P1",
        "verification_window_days": 0,
        "rationale_short": "复查/就医协助优先于普通健康动作",
        "safety_status": "needs_doctor",
    },
    "data_quality": {
        "upstreamness": 3,
        "actionability": 3,
        "frequency": 2,
        "verifiability": 4,
        "confidence": "medium",
        "friction": 2,
        "priority_tier": "P3",
        "verification_window_days": 0,
        "rationale_short": "先核对数据来源, 避免用低置信数据生成动作",
    },
    "correction": {
        "upstreamness": 4,
        "actionability": 4,
        "frequency": 3,
        "verifiability": 4,
        "confidence": "medium",
        "friction": 2,
        "priority_tier": "P2",
        "verification_window_days": 14,
        "rationale_short": "连续跳过或结果不佳, 需要调整动作而非继续轰炸",
    },
}


def _profile_for(item: Dict[str, Any]) -> Dict[str, Any]:
    profile = dict(_DEFAULT_PROFILE)
    profile.update(_KIND_PROFILES.get(str(item.get("type") or ""), {}))

    if item.get("type") == "checkup" and item.get("status") == "overdue":
        profile["priority_tier"] = "P0"
        profile["safety_status"] = "needs_doctor"
        profile["rationale_short"] = "安全/复查事项先于普通杠杆排序"

    if item.get("type") == "training" and item.get("light") == "red":
        profile["priority_tier"] = "P1"
        profile["rationale_short"] = "恢复不足时先降训练强度, 避免过度负荷"

    return profile


def _score(item: Dict[str, Any], profile: Dict[str, Any]) -> int:
    confidence = _CONFIDENCE_WEIGHT.get(str(profile["confidence"]), 0.8)
    leverage = (
        float(profile["upstreamness"])
        * float(profile["actionability"])
        * float(profile["frequency"])
        * float(profile["verifiability"])
        * confidence
    )
    friction_penalty = float(profile["friction"]) * 4
    agenda_priority = min(max(int(item.get("priority") or 0), 0), 100)
    tier_boost = max(0, 4 - _TIER_ORDER.get(str(profile["priority_tier"]), 2)) * 30
    return int(round(leverage - friction_penalty + agenda_priority + tier_boost))


def rank_agenda_action(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of an agenda item annotated with leverage metadata."""
    profile = _profile_for(item)
    ranked = dict(item)
    ranked.update({
        "leverage_score": _score(item, profile),
        "rationale_short": profile["rationale_short"],
        "verification_window_days": profile["verification_window_days"],
        "priority_tier": profile["priority_tier"],
        "safety_status": profile.get("safety_status", "allowed"),
    })
    return ranked


def rank_agenda_actions(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank agenda items by safety tier, leverage score, and agenda priority."""
    ranked = [rank_agenda_action(i) for i in items]
    ranked.sort(
        key=lambda i: (
            _TIER_ORDER.get(str(i.get("priority_tier")), 2),
            -(i.get("leverage_score") or 0),
            -(i.get("priority") or 0),
        )
    )
    return ranked
