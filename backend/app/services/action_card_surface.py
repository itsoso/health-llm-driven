"""
action_card_surface —— 把 Safety alert / Specialist finding 等系统产出,
surface 到 action_cards 作为用户可决策、可追踪的条目.

设计要点:
- 旁路写入: 任何异常都不应影响上游 Safety/Orchestrator 主流程.
- 幂等: 同一 (user_id, source_type, source_id) 若已有 user_decision IS NULL 的活动卡,
  则不再新建. 这避免 Safety API 每 5 分钟命中缓存失效时刷一堆重复卡.
- 只更新内容/严重度: 规则触发多次, 严重度可能变化. 更新而不是新建.
- 新卡 status 默认 'active', user_decision NULL, 等用户决策.
"""

from __future__ import annotations

import logging
from typing import Collection, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.agents.safety_guardian.schema import Alert, Severity
from app.models.action_card import ActionCard

logger = logging.getLogger(__name__)


_SEVERITY_TO_LABEL = {
    Severity.INFO: "info",
    Severity.LOW: "low",
    Severity.MEDIUM: "medium",
    Severity.HIGH: "high",
    Severity.CRITICAL: "critical",
}


def surface_safety_alert(
    db: Session,
    user_id: int,
    alert: Alert,
) -> Optional[int]:
    """
    把单条 Safety alert upsert 到 action_cards, 返回 card_id. 失败返回 None.

    幂等策略: 查 (user_id, source_type='safety_alert', source_id=rule_id)
    且 user_decision IS NULL 的活动卡:
      - 找到 → 更新 severity/title/content (规则可能重新评估出更高严重度)
      - 没找到 → 新建
    一旦用户做过决策 (accepted/declined/false_positive/...), 这条路径不再触碰,
    下次同 rule 触发会新建一张 "复发" 卡.
    """
    try:
        existing = (
            db.query(ActionCard)
            .filter(
                ActionCard.user_id == user_id,
                ActionCard.source_type == "safety_alert",
                ActionCard.source_id == alert.rule_id,
                ActionCard.user_decision.is_(None),
            )
            .order_by(ActionCard.created_at.desc())
            .first()
        )

        severity_label = _SEVERITY_TO_LABEL.get(alert.severity, "info")

        if existing is not None:
            updated = False
            if existing.status != "active":
                existing.status = "active"
                updated = True
            if existing.is_visible is not True:
                existing.is_visible = True
                updated = True
            if existing.severity != severity_label:
                existing.severity = severity_label
                updated = True
            if existing.title != alert.title:
                existing.title = alert.title
                updated = True
            if existing.content != alert.message:
                existing.content = alert.message
                updated = True
            if updated:
                db.commit()
                db.refresh(existing)
            return existing.id

        card = ActionCard(
            user_id=user_id,
            title=alert.title,
            content=alert.message,
            card_type="alert",
            source_type="safety_alert",
            source_id=alert.rule_id,
            severity=severity_label,
            status="active",
            priority=int(alert.severity),
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        logger.info(
            f"[action_card_surface] 新建 safety card user={user_id} "
            f"rule={alert.rule_id} severity={severity_label} card_id={card.id}"
        )
        return card.id

    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[action_card_surface] 写入失败 (user={user_id}, rule={alert.rule_id}): {e}"
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None


def surface_safety_alerts(
    db: Session,
    user_id: int,
    alerts: Iterable[Alert],
    *,
    reconcile_rule_ids: Optional[Collection[str]] = None,
) -> List[int]:
    """批量 surface，并归档已不再触发的指定规则卡片。"""
    alerts = list(alerts)
    ids: List[int] = []
    for alert in alerts:
        cid = surface_safety_alert(db, user_id, alert)
        if cid is not None:
            ids.append(cid)

    if reconcile_rule_ids:
        active_rule_ids = {alert.rule_id for alert in alerts}
        stale_rule_ids = set(reconcile_rule_ids) - active_rule_ids
        if stale_rule_ids:
            try:
                stale_cards = (
                    db.query(ActionCard)
                    .filter(
                        ActionCard.user_id == user_id,
                        ActionCard.source_type == "safety_alert",
                        ActionCard.source_id.in_(stale_rule_ids),
                        ActionCard.user_decision.is_(None),
                    )
                    .all()
                )
                changed = False
                for card in stale_cards:
                    if card.status != "archived":
                        card.status = "archived"
                        changed = True
                    if card.is_visible is not False:
                        card.is_visible = False
                        changed = True
                if changed:
                    db.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "[action_card_surface] reconcile 失败 "
                    f"(user={user_id}, rules={sorted(stale_rule_ids)}): {e}"
                )
                try:
                    db.rollback()
                except Exception:
                    pass
    return ids
