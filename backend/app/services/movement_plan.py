"""movement_plan —— Mobile 我的运动方案 API (G-W6, 2026-05-12).

包装 MovementCoachSpecialist 输出 + 关联 action_cards (用户接受过的训练建议).

返回结构 (mobile 直接渲染):
  {
    has_data: bool,
    summary: "训练负荷最佳区 (ACWR 0.95) · 今日建议 zone2",
    training_status: { status, status_zh, source, acwr, garmin_load_ratio, ... },
    today: { intensity, guidance, based_on_readiness },
    fitness: { vo2max_running, vo2max_cycling, resting_hr },
    gene_bias: { actn3?, ppargc1a?, nos3?, col5a1?, ... },
    week_adjustment: "建议本周减量 ...",
    recent_workouts: [...],
    proposed_experiments: [{title, content, metric_key, baseline_value, target_value, ...}],
    related_cards: [{ id, title, status, user_decision, outcome, effect_size, ... }],
  }
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.orchestrator.schema import Intent
from app.services.outcome_safety import user_facing_efficacy_fields

logger = logging.getLogger(__name__)


_STATUS_ZH = {
    "optimal": "负荷最佳区",
    "peaking": "接近峰值",
    "overload": "过载风险",
    "undertrained": "负荷偏低",
    "detraining": "脱训阶段",
    "building": "负荷构建中",
    "unknown": "负荷未知",
}

_INTENSITY_ZH = {
    "high": "高强度",
    "moderate": "中等强度",
    "low": "低强度",
    "rest": "休息",
    "active_recovery": "主动恢复",
    "deload": "减量",
}


def _fetch_movement_related_cards(db: Session, user_id: int) -> List[ActionCard]:
    """近 90 天 user 的训练/运动相关卡, 按关键词模糊匹配."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    keys = ["训练", "运动", "跑", "骑", "深蹲", "deload", "ACWR", "心率区", "z2", "zone 2",
            "有氧", "力量", "高强度", "主动恢复"]
    cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.created_at >= cutoff,
        )
        .order_by(desc(ActionCard.created_at))
        .limit(200)
        .all()
    )
    matched = []
    for c in cards:
        haystack = (c.title or "") + " " + (c.content or "")
        if any(k in haystack for k in keys):
            matched.append(c)
            if len(matched) >= 10:
                break
    return matched


def _card_to_dict(card: ActionCard) -> Dict[str, Any]:
    efficacy_fields = user_facing_efficacy_fields(card)
    return {
        "id": card.id,
        "title": card.title,
        "status": card.status,
        "user_decision": card.user_decision,
        **efficacy_fields,
        "metric_key": card.metric_key,
        "baseline_value": card.baseline_value,
        "actual_value": card.actual_value,
        "evidence_level": card.evidence_level,
        "evidence_refs": card.evidence_refs or [],
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "completed_at": card.completed_at.isoformat() if card.completed_at else None,
        "graded_at": card.graded_at.isoformat() if card.graded_at else None,
    }


def build_movement_plan(db: Session, user_id: int) -> Dict[str, Any]:
    """主入口: 调 MovementCoachSpecialist + Twin + 关联 action_cards."""
    from app.agents.movement_coach.coach import MovementCoachSpecialist
    from app.twin import build_twin

    try:
        twin = build_twin(db, user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[movement_plan] twin build 失败 user={user_id}: {e}")
        return {
            "has_data": False,
            "error": "twin_build_failed",
        }

    coach = MovementCoachSpecialist()
    fake_intent = Intent(raw_query="本周运动方案", categories=["movement"], keywords=[])
    if not coach.applies_to(fake_intent, twin):
        # 没数据也强跑 — 让用户看到"暂无数据"提示而不是空响应
        pass

    try:
        finding = coach.run(twin, {"query": "本周运动方案", "db": db})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[movement_plan] coach run 失败 user={user_id}: {e}")
        return {
            "has_data": False,
            "error": "coach_run_failed",
        }

    # 拆分 finding.findings 按 type
    blocks_by_type: Dict[str, Any] = {}
    for f in finding.findings:
        t = f.get("type")
        if t in {"training_status", "today_prescription", "fitness_snapshot",
                 "week_adjustment", "recent_workout_detail"}:
            blocks_by_type[t] = f
        elif t == "gene_bias":
            blocks_by_type.setdefault("gene_biases", []).append(f)

    # ProposedCard → 序列化 (它是 pydantic-like 对象)
    experiments = []
    for pc in (finding.proposed_cards or []):
        if hasattr(pc, "model_dump"):
            experiments.append(pc.model_dump())
        elif hasattr(pc, "__dict__"):
            experiments.append(dict(pc.__dict__))

    # 关联 action_cards
    related = _fetch_movement_related_cards(db, user_id)

    # status_zh + intensity_zh
    ts_block = blocks_by_type.get("training_status", {})
    today_block = blocks_by_type.get("today_prescription", {})
    status = ts_block.get("status", "unknown")
    intensity = today_block.get("intensity", "moderate")

    return {
        "has_data": True,
        "summary": finding.summary or "",
        "training_status": {
            **ts_block,
            "status_zh": _STATUS_ZH.get(status, status),
        },
        "today": {
            **today_block,
            "intensity_zh": _INTENSITY_ZH.get(intensity, intensity),
        },
        "fitness": blocks_by_type.get("fitness_snapshot"),
        "gene_biases": blocks_by_type.get("gene_biases", []),
        "week_adjustment": (blocks_by_type.get("week_adjustment") or {}).get("text"),
        "recent_workouts": blocks_by_type.get("recent_workout_detail"),
        "proposed_experiments": experiments,
        "related_cards": [_card_to_dict(c) for c in related],
    }
