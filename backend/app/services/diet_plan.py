"""diet_plan —— Mobile 我的饮食方案 API (G-W7, 2026-05-12).

包装 FuelStrategistSpecialist 输出 + 关联 action_cards (饮食类).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.services.outcome_safety import user_facing_efficacy_fields

logger = logging.getLogger(__name__)


def _related_card_dedupe_key(card: ActionCard) -> str:
    """Return a stable semantic-ish key for related-card de-duplication.

    Action cards can be generated repeatedly by the agent across chats and
    daily plans. The diet plan only needs one row per accepted suggestion topic;
    otherwise the mobile page becomes dominated by repeated "MTHFR..." cards.
    """
    title = re.sub(r"\s+", "", (card.title or "").strip().lower())
    if title:
        return f"title:{title}"
    content = re.sub(r"\s+", "", (card.content or "").strip().lower())
    return f"content:{content[:120]}"


def _fetch_diet_related_cards(db: Session, user_id: int) -> List[ActionCard]:
    """近 90 天饮食/营养相关卡, 按关键词模糊匹配."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    keys = [
        "饮食", "营养", "蛋白", "热量", "碳水", "脂肪", "饮水",
        "餐", "早餐", "午餐", "晚餐", "Omega-3", "EPA", "DHA",
        "维 D", "维D", "B12", "叶酸", "5-MTHF", "钙", "铁", "锌", "镁",
        "胆固醇", "LDL", "血糖", "HbA1c",
    ]
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
    seen_keys = set()
    for c in cards:
        haystack = (c.title or "") + " " + (c.content or "")
        if any(k in haystack for k in keys):
            dedupe_key = _related_card_dedupe_key(c)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
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
        "graded_at": card.graded_at.isoformat() if card.graded_at else None,
    }


def build_diet_plan(db: Session, user_id: int) -> Dict[str, Any]:
    from app.agents.fuel_strategist.strategist import FuelStrategistSpecialist
    from app.services.knowledge_evidence import build_advice_knowledge_context
    from app.twin import build_twin

    try:
        twin = build_twin(db, user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[diet_plan] twin build 失败 user={user_id}: {e}")
        return {"has_data": False, "error": "twin_build_failed"}

    strategist = FuelStrategistSpecialist()
    knowledge_evidence = build_advice_knowledge_context(
        domains=["nutrition", "supplement"],
        user_signals=[
            "metabolic health",
            "protein target",
            "weight management",
            "supplement safety",
        ],
    )
    try:
        finding = strategist.run(
            twin,
            {
                "query": "本周饮食营养状态",
                "db": db,
                "knowledge_evidence": knowledge_evidence,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[diet_plan] strategist run 失败 user={user_id}: {e}")
        return {"has_data": False, "error": "strategist_run_failed"}

    blocks_by_type: Dict[str, Any] = {}
    for f in finding.findings:
        t = f.get("type")
        if t == "gene_nudge":
            blocks_by_type.setdefault("gene_nudges", []).append(f)
        else:
            blocks_by_type[t] = f

    experiments = []
    for pc in (finding.proposed_cards or []):
        if hasattr(pc, "model_dump"):
            experiments.append(pc.model_dump())
        elif hasattr(pc, "__dict__"):
            experiments.append(dict(pc.__dict__))

    related = _fetch_diet_related_cards(db, user_id)

    return {
        "has_data": True,
        "summary": finding.summary or "",
        "energy": blocks_by_type.get("energy"),
        "protein": blocks_by_type.get("protein"),
        "hydration": blocks_by_type.get("hydration"),
        "next_meal": blocks_by_type.get("next_meal"),
        "supplement": blocks_by_type.get("supplement"),
        "gene_nudges": blocks_by_type.get("gene_nudges", []),
        "labs_concern": blocks_by_type.get("labs_concern"),
        "knowledge_evidence": knowledge_evidence,
        "proposed_experiments": experiments,
        "related_cards": [_card_to_dict(c) for c in related],
    }
