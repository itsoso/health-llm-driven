# -*- coding: utf-8 -*-
"""依从性智能任务 —— N-of-1 掉队再激活(Next Horizon Tier 2)。

每周扫"已接受、未评分"的在飞 N-of-1 卡,挑掉队风险(快到期没动 / 已逾期没复检),
每人至多温和推一条,且**走全局打扰预算**(与 longevity/trajectory 共享,不叠加扰民)。
直接抬北极星:完成闭环且改善的用户(掉队的多半是没坚持完,不是无效)。

纯判定在 services/adherence_watch.py(可测);本文件只取数 + 推送 + 埋点。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import List

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.action_card import ActionCard
from app.services.adherence_watch import AtRiskCard, at_risk_cards
from app.utils.async_helpers import run_async

logger = logging.getLogger(__name__)

_AGENT_TYPE = "adherence_watch"
_ACCEPTED = ("accepted", "adjusted")


def evaluate_user_adherence(db, user_id: int, now: datetime | None = None) -> List[AtRiskCard]:
    """取用户在飞 N-of-1 卡,返回掉队风险(可测,无副作用)。"""
    now = now or datetime.now(UTC)
    cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user_id,
            ActionCard.outcome.is_(None),
            ActionCard.user_decision.in_(_ACCEPTED),
            ActionCard.verification_days.isnot(None),
        )
        .all()
    )
    return at_risk_cards(cards, now)


@celery_app.task
def adherence_watch():
    """每周扫描:N-of-1 掉队再激活(每人至多一条,走全局打扰预算)。"""
    from app.agents.audit import log_proactive_trigger
    from app.services.notification.push_service import PushService
    from app.services.adherence_watch import nudge_text
    from app.services.proactive_coordinator import can_notify_proactively

    logger.info("[依从监测] 开始 N-of-1 掉队扫描")
    triggered = notified = 0
    now = datetime.now(UTC)
    with SessionLocal() as db:
        user_ids = [
            uid for (uid,) in db.query(ActionCard.user_id)
            .filter(
                ActionCard.outcome.is_(None),
                ActionCard.user_decision.in_(_ACCEPTED),
                ActionCard.verification_days.isnot(None),
            ).distinct().all()
        ]
        push_service = PushService(db)
        for user_id in user_ids:
            try:
                risks = evaluate_user_adherence(db, user_id, now)
                if not risks:
                    continue
                triggered += len(risks)
                # 逾期优先,其次最接近到期;每人至多一条
                top = sorted(risks, key=lambda r: (r.kind != "overdue", r.days_left))[0]
                do_notify = can_notify_proactively(db, user_id)
                if do_notify:
                    title, msg = nudge_text(top)
                    run_async(push_service.send_notification(
                        user_id=user_id,
                        notification_type="reminder",
                        title=title,
                        content=msg,
                        # §5:卡片标题只进 data(锁屏文案已泛化),App 解锁后渲染
                        data={"kind": "adherence", "card_id": top.card_id,
                              "card_title": top.title, "risk": top.kind},
                        severity="info",
                    ))
                    notified += 1
                for r in risks:
                    log_proactive_trigger(
                        db, user_id, agent_type=_AGENT_TYPE,
                        metric=r.metric or "adherence", kind=r.kind, delta=0.0,
                        notable=True, notified=(do_notify and r.card_id == top.card_id),
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[依从监测] user={user_id} 处理失败: {e}")
    logger.info(f"[依从监测] 完成:风险 {triggered} 项,推送 {notified} 人")
    return {"triggered": triggered, "notified": notified}
