"""Transactional registration events and bounded, retryable admin delivery."""
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.phone_auth import RegistrationAdminNotification
from app.models.user import User
from app.services.notification.push_privacy import llm_push_backstop
from app.services.notification.telegram_push import TelegramPushService
from app.services.phone_auth import mask_phone

logger = logging.getLogger(__name__)


def enqueue_registration_notification(db: Session, user: User) -> None:
    """Call only when inserting a new user, before that transaction commits."""
    db.flush()
    db.add(RegistrationAdminNotification(user_id=user.id))
    db.flush()


def registration_message(event: RegistrationAdminNotification, user: User) -> str:
    created_at = event.created_at
    if created_at.tzinfo is None:  # SQLite compatibility; PostgreSQL stores aware timestamps.
        created_at = created_at.replace(tzinfo=UTC)
    timestamp = created_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    content = f"事件编号：{event.id}\n用户编号：{user.id}\n注册时间：{timestamp}（北京时间）"
    if user.phone:
        content += f"\n手机号：{mask_phone(user.phone)}"
    title, content, _ = llm_push_backstop(
        "新用户注册", content,
        generic_title="新用户注册", generic_content="有新用户完成注册，请进入管理后台查看。",
    )
    return f"{title}\n{content}"


async def deliver_registration_notifications(db: Session, *, limit: int = 10) -> dict:
    """At-least-once delivery; row locks prevent concurrent workers claiming one event.

    A crash after Telegram accepts but before commit can resend the same event ID.
    No raw response, exception, phone, or credential is persisted as an error.
    """
    counts = {"sent": 0, "failed": 0}
    sender = TelegramPushService()
    for _ in range(min(max(limit, 0), 20)):
        now = datetime.now(UTC)
        try:
            event = (
                db.query(RegistrationAdminNotification)
                .filter(RegistrationAdminNotification.status == "pending",
                        RegistrationAdminNotification.next_attempt_at <= now)
                .order_by(RegistrationAdminNotification.next_attempt_at, RegistrationAdminNotification.id)
                .with_for_update(skip_locked=True)
                .first()
            )
            if event is None:
                db.rollback()
                break
            user = db.get(User, event.user_id)
            if user is None:
                raise RuntimeError("registration notification owner missing")
            result = await sender.send_message(registration_message(event, user), parse_mode=None)
            event.attempts += 1
            if result.get("success") is True:
                event.status = "sent"
                event.sent_at = datetime.now(UTC)
                event.last_error = None
                counts["sent"] += 1
            else:
                reason = result.get("reason")
                event.last_error = reason if reason in {
                    "not_configured", "no_chat_id", "transport_error", "telegram_rejected", "invalid_response"
                } else "delivery_failed"
                event.next_attempt_at = now + timedelta(seconds=min(3600, 60 * 2 ** min(event.attempts - 1, 6)))
                counts["failed"] += 1
                logger.warning("registration notification pending event_id=%s reason=%s", event.id, event.last_error)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return counts
