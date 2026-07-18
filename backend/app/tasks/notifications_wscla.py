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

from sqlalchemy import Text, cast, distinct

from app.database import SessionLocal
from app.models.action_card import ActionCard
from app.models.daily_health import GarminData
from app.models.notification import NotificationLog, NotificationStatus
from app.models.user import User
from app.services.notification.push_privacy import is_sensitive_alert
from app.services.notification.push_service import CRITICAL_DEDUP_WINDOW_HOURS, PushService
from app.services.weekly_advisor import generate_weekly_advice
from app.utils.async_helpers import run_async
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)

MAX_UNDELIVERED_ESCALATION_RETRIES = 3
PENDING_DELIVERY_GRACE_HOURS = 1


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _apply_undelivered_retry(meta: dict, now: datetime, reason: str | None) -> bool:
    """Record one undelivered escalation and return whether the retry budget is exhausted."""
    failures = max(0, int(meta.get("escalation_delivery_failures") or 0)) + 1
    meta["escalation_delivery_failures"] = failures
    meta["last_escalation_delivery_failure_at"] = now.isoformat()
    meta["last_escalation_delivery_failure_reason"] = reason or "unknown"
    meta.pop("escalation_pending_delivery_at", None)
    meta.pop("escalation_pending_expected_count", None)
    meta.pop("escalation_pending_until", None)

    if failures >= MAX_UNDELIVERED_ESCALATION_RETRIES:
        meta["escalation_delivery_blocked_at"] = now.isoformat()
        meta.pop("escalation_retry_after", None)
        return True

    # A critical dedup may only clear after the dedicated 3h window. Other failures
    # retry with bounded exponential backoff: 1h, then 2h, then stop.
    retry_hours = (
        CRITICAL_DEDUP_WINDOW_HOURS
        if reason == "dedup"
        else 2 ** (failures - 1)
    )
    meta["escalation_retry_after"] = (now + timedelta(hours=retry_hours)).isoformat()
    return False


def _sent_escalation_logs_for_update(db):
    """Return only sent escalation logs and lock them for one flush worker.

    A blanket lock over all sent notification logs would turn a five-minute
    maintenance task into a global notification bottleneck. JSON is stored as
    text in SQLite tests and JSONB in PostgreSQL, so casting to text keeps the
    marker filter portable while the Python guard remains the final authority.
    """
    return db.query(NotificationLog).filter(
        NotificationLog.status == NotificationStatus.SENT.value,
        NotificationLog.notification_type == "health_alert",
        cast(NotificationLog.data, Text).like('%"escalation_action_card_id"%'),
    ).with_for_update(skip_locked=True)


def _account_sent_delayed_escalations(db, now: datetime) -> int:
    """Commit an escalation slot only after a delayed NotificationLog becomes SENT.

    The delayed queue only promises a future attempt. A transport or channel failure
    during flush must not silently consume a user's critical-escalation budget.
    """
    accounted = 0
    logs = _sent_escalation_logs_for_update(db).all()
    for log in logs:
        data = dict(log.data or {})
        if data.get("escalation_delivery_accounted"):
            continue
        card_id = data.get("escalation_action_card_id")
        expected_count = data.get("escalation_expected_count")
        if not isinstance(card_id, int) or not isinstance(expected_count, int):
            continue

        card = db.query(ActionCard).filter(
            ActionCard.id == card_id,
            ActionCard.user_id == log.user_id,
        ).one_or_none()
        if card and card.status == "active" and card.user_decision is None:
            meta = dict(card.latest_assessment or {})
            current_count = max(0, int(meta.get("escalation_count") or 0))
            if expected_count > current_count:
                sent_at = log.sent_at
                # SQLite test storage may round-trip a timezone-aware datetime as
                # naive, while PostgreSQL preserves the offset. Metadata must remain
                # timezone-aware on both paths.
                if sent_at is None or sent_at.tzinfo is None:
                    sent_at = now
                meta["escalation_count"] = expected_count
                meta["last_escalated_at"] = sent_at.isoformat()
                meta["escalation_delivery_failures"] = 0
                meta.pop("escalation_pending_delivery_at", None)
                meta.pop("escalation_pending_expected_count", None)
                meta.pop("escalation_pending_until", None)
                meta.pop("escalation_retry_after", None)
                card.latest_assessment = meta
                accounted += 1

        # Mark even if the card was resolved or already advanced: replaying a SENT log
        # must never increment an escalation budget twice.
        data["escalation_delivery_accounted"] = True
        log.data = data

    if accounted or any(
        (log.data or {}).get("escalation_delivery_accounted") for log in logs
    ):
        db.commit()
    return accounted


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
            result["escalation_accounted"] = _account_sent_delayed_escalations(
                db, get_china_now()
            )
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
        undelivered = 0
        pending = 0
        delivery_blocked = 0

        for card in cards:
            meta = dict(card.latest_assessment or {})
            escalation_count = meta.get("escalation_count", 0)
            last_escalated_at = meta.get("last_escalated_at")

            if meta.get("escalation_delivery_blocked_at"):
                skipped += 1
                delivery_blocked += 1
                continue

            retry_after = _parse_timestamp(meta.get("escalation_retry_after"))
            if retry_after and now < retry_after.replace(tzinfo=now.tzinfo):
                skipped += 1
                continue

            pending_until = _parse_timestamp(meta.get("escalation_pending_until"))
            if pending_until:
                grace_until = pending_until + timedelta(hours=PENDING_DELIVERY_GRACE_HOURS)
                if now <= grace_until.replace(tzinfo=now.tzinfo):
                    skipped += 1
                    continue
                blocked = _apply_undelivered_retry(
                    meta, now, "delayed_delivery_unconfirmed"
                )
                card.latest_assessment = meta
                db.commit()
                undelivered += 1
                delivery_blocked += int(blocked)
                logger.warning(
                    "[escalate_critical] card=%s delayed escalation was not confirmed "
                    "by flush → retry state recorded",
                    card.id,
                )
                continue

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
                # §5 推送隐私:ddi/dsi/pgx/labs/problem_red_lines 来源的卡片
                # title/content 带药名/化验项/诊断 → 锁屏泛化;其余急性类
                # (vitals/cgm/symptoms)原文透传(时效安全信息)。
                if is_sensitive_alert(rule_id=card.source_id):
                    esc_title = "⚠️ 仍有一条紧急健康告警未处理"
                    esc_content = "24 小时前的重要告警还没确认,点开查看详情并处理。"
                else:
                    esc_title = f"⚠️ 仍未处理: {card.title}"
                    esc_content = card.content
                result = run_async(push_service.send_notification(
                    user_id=card.user_id,
                    notification_type="health_alert",
                    title=esc_title,
                    content=esc_content,
                    severity="critical",
                    data={
                        "rule_id": card.source_id,
                        "action_card_id": card.id,
                        "escalation": True,
                        "escalation_count": escalation_count + 1,
                        "escalation_action_card_id": card.id,
                        "escalation_expected_count": escalation_count + 1,
                    },
                )) or {}

                reason = result.get("reason")
                if reason == "delayed_for_quiet_hours":
                    scheduled_at = _parse_timestamp(result.get("scheduled_at")) or now
                    meta["escalation_pending_delivery_at"] = now.isoformat()
                    meta["escalation_pending_expected_count"] = escalation_count + 1
                    meta["escalation_pending_until"] = scheduled_at.isoformat()
                    card.latest_assessment = meta
                    db.commit()
                    pending += 1
                    continue

                if not result.get("success"):
                    undelivered += 1
                    blocked = _apply_undelivered_retry(meta, now, reason)
                    card.latest_assessment = meta
                    db.commit()
                    delivery_blocked += int(blocked)
                    logger.warning(
                        "[escalate_critical] card=%s 升级推送未送达 reason=%s → "
                        "不消耗 escalation 名额 (count 仍为 %s), %s",
                        card.id,
                        reason or "unknown",
                        escalation_count,
                        "已停止自动重试" if blocked else "已记录退避后重试",
                    )
                    continue

                meta["escalation_count"] = escalation_count + 1
                meta["last_escalated_at"] = now.isoformat()
                meta["escalation_delivery_failures"] = 0
                meta.pop("escalation_retry_after", None)
                card.latest_assessment = meta
                db.commit()
                escalated += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"[escalate_critical] card={card.id} 失败: {e}"
                )

    if escalated or skipped or undelivered or pending:
        logger.info(
            f"[escalate_critical] escalated={escalated} skipped={skipped} "
            f"undelivered={undelivered} pending={pending} blocked={delivery_blocked} "
            f"checked={len(cards) if cards else 0}"
        )
    return {
        "escalated": escalated,
        "skipped": skipped,
        "undelivered": undelivered,
        "pending": pending,
        "delivery_blocked": delivery_blocked,
    }


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
