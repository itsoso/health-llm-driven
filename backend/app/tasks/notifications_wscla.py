"""WSCLA 相关任务实现 (P1-1 / P1-7 / P2-1).

从 notifications.py 拆出, 这里是**纯函数**, 不带 @celery_app.task 装饰器.
notifications.py 里的同名任务 wrapper 保留 'app.tasks.notifications.X' task name,
内部 import 本模块的纯函数实现. celery beat schedule 不动.

函数:
- flush_delayed_pushes_impl (P1-1): 静默时段后批量 fire 延迟推送
- escalate_critical_unresolved_impl (P1-7): Critical 24h 未决策升级再推
- weekly_advisor_run_impl (P2-1): 周日 21:07 产 3-5 条本周建议
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import distinct

from app.database import SessionLocal
from app.models.action_card import ActionCard
from app.models.daily_health import GarminData
from app.models.user import User
from app.services.notification.push_service import PushService
from app.services.weekly_advisor import generate_weekly_advice
from app.utils.async_helpers import run_async
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)


def flush_delayed_pushes_impl():
    """每 5 分钟扫一次 NotificationLog 里 status='delayed' 且 scheduled_at <= now 的记录,
    重新走 send_notification (respect_quiet_hours=False) fire 出去.

    严格不打扰睡眠 (2026-05-11): 静默时段所有 severity 都进 delayed 队列,
    quiet_hours_end 后由本任务批量 fire.
    """
    with SessionLocal() as db:
        push_service = PushService(db)
        try:
            result = run_async(push_service.flush_delayed_pushes())
            if result.get("flushed", 0) > 0:
                logger.info(f"[FlushDelayedPushes] {result}")
            return result
        except Exception as e:  # noqa: BLE001
            logger.error(f"[FlushDelayedPushes] 失败: {e}", exc_info=True)
            return {"flushed": 0, "succeeded": 0, "failed": 0, "error": str(e)}


def escalate_critical_unresolved_impl():
    """每小时跑: Critical 告警 24h 内未 decided 且 push 已发 → 升级再推 (max 3 次).

    严格不打扰睡眠 (2026-05-11): 升级推送命中静默时段也走 delayed 队列, 不强推.
    使用 latest_assessment.escalation_count + last_escalated_at 跟踪重推次数.
    """
    MAX_ESCALATIONS = 3
    MIN_GAP_HOURS = 12

    now = get_china_now()
    cutoff = now - timedelta(hours=24)
    min_gap_cutoff = now - timedelta(hours=MIN_GAP_HOURS)

    with SessionLocal() as db:
        cards = db.query(ActionCard).filter(
            ActionCard.severity == "critical",
            ActionCard.user_decision.is_(None),
            ActionCard.status == "active",
            ActionCard.push_sent_at.isnot(None),
            ActionCard.push_sent_at < cutoff,
        ).limit(50).all()

        push_service = PushService(db)
        escalated = 0
        skipped = 0

        for card in cards:
            meta = dict(card.latest_assessment or {})
            escalation_count = meta.get("escalation_count", 0)
            last_escalated_at = meta.get("last_escalated_at")

            if escalation_count >= MAX_ESCALATIONS:
                skipped += 1
                continue

            if last_escalated_at:
                try:
                    last_dt = datetime.fromisoformat(last_escalated_at.replace("Z", "+00:00"))
                    if last_dt > min_gap_cutoff.replace(tzinfo=last_dt.tzinfo):
                        skipped += 1
                        continue
                except Exception:
                    pass

            try:
                run_async(push_service.send_notification(
                    user_id=card.user_id,
                    notification_type="health_alert",
                    title=f"⚠️ 仍未处理: {card.title}",
                    content=card.content,
                    severity="critical",
                    data={
                        "rule_id": card.source_id,
                        "action_card_id": card.id,
                        "escalation": True,
                        "escalation_count": escalation_count + 1,
                    },
                ))
                meta["escalation_count"] = escalation_count + 1
                meta["last_escalated_at"] = now.isoformat()
                card.latest_assessment = meta
                db.commit()
                escalated += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"[escalate_critical] card={card.id} 失败: {e}"
                )

    if escalated or skipped:
        logger.info(
            f"[escalate_critical] escalated={escalated} skipped={skipped} "
            f"checked={len(cards) if cards else 0}"
        )
    return {"escalated": escalated, "skipped": skipped}


def weekly_advisor_run_impl():
    """每周日 21:07 跑: 给所有 7 天内活跃用户产 3-5 条本周建议, 写 action_cards.

    幂等: 本周已有 weekly_advisor 卡的用户跳过.
    """
    logger.info("[WeeklyAdvisor] 开始本周建议产出")
    cutoff = (get_china_now() - timedelta(days=7)).date()

    with SessionLocal() as db:
        user_ids = [
            r[0] for r in db.query(distinct(GarminData.user_id))
            .filter(GarminData.record_date >= cutoff)
            .all()
        ]
        if not user_ids:
            user_ids = [
                r[0] for r in db.query(User.id)
                .filter(User.is_active == True, User.is_approved == True)  # noqa: E712
                .all()
            ]

    logger.info(f"[WeeklyAdvisor] 候选用户 {len(user_ids)} 个")

    total_created = 0
    total_skipped = 0
    total_fallback = 0
    failed = 0

    for uid in user_ids:
        try:
            with SessionLocal() as db:
                result = run_async(generate_weekly_advice(db, uid))
            created = result.get("created", 0)
            if created > 0:
                total_created += created
                if result.get("fallback"):
                    total_fallback += 1
            else:
                total_skipped += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(f"[WeeklyAdvisor] user={uid} 失败: {e}")

    logger.info(
        f"[WeeklyAdvisor] 完成: created={total_created} "
        f"users_done={len(user_ids) - total_skipped - failed}/{len(user_ids)} "
        f"skipped={total_skipped} fallback={total_fallback} failed={failed}"
    )
    return {
        "users_total": len(user_ids),
        "created": total_created,
        "skipped": total_skipped,
        "fallback": total_fallback,
        "failed": failed,
    }
