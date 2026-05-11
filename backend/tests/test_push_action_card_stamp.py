"""test_push_action_card_stamp —— push_sent_at 回写到 action_cards (Phase 0 · W1)."""

from app.models.action_card import ActionCard
from app.models.notification import NotificationStatus
from app.models.user import User
from app.services.notification.push_service import PushService


def _make_user(db, username="stamp_user"):
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        name=username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_card(db, user_id):
    card = ActionCard(
        user_id=user_id,
        title="推送测试卡",
        content="c",
        card_type="alert",
        source_type="safety_alert",
        source_id="vitals.hr_spike",
        severity="high",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def test_push_sent_stamps_action_card(db):
    user = _make_user(db)
    card = _make_card(db, user.id)
    svc = PushService(db)

    svc._log_notification_multi(
        user_id=user.id,
        notification_type="safety_alert",
        title=card.title,
        content=card.content,
        data={"action_card_id": card.id, "rule_id": "vitals.hr_spike"},
        status=NotificationStatus.SENT.value,
        channels=[{"name": "ios", "status": "sent", "error": None}],
    )

    db.refresh(card)
    assert card.push_sent_at is not None


def test_push_failed_does_not_stamp(db):
    user = _make_user(db, username="failed_stamp")
    card = _make_card(db, user.id)
    svc = PushService(db)

    svc._log_notification_multi(
        user_id=user.id,
        notification_type="safety_alert",
        title=card.title,
        content=card.content,
        data={"action_card_id": card.id},
        status=NotificationStatus.FAILED.value,
        channels=[{"name": "ios", "status": "failed", "error": "apns_down"}],
        error_message="apns_down",
    )

    db.refresh(card)
    assert card.push_sent_at is None


def test_push_without_action_card_id_is_noop(db):
    """老路径: 不带 action_card_id 的 push 不影响任何卡."""
    user = _make_user(db, username="noop_stamp")
    card = _make_card(db, user.id)
    svc = PushService(db)

    svc._log_notification_multi(
        user_id=user.id,
        notification_type="daily_summary",
        title="每日摘要",
        content="...",
        data={"foo": "bar"},
        status=NotificationStatus.SENT.value,
        channels=[{"name": "ios", "status": "sent", "error": None}],
    )

    db.refresh(card)
    assert card.push_sent_at is None


def test_push_idempotent_does_not_overwrite(db):
    """同一卡再收到 push SENT 事件, 首次时间不被覆盖."""
    user = _make_user(db, username="idem_stamp")
    card = _make_card(db, user.id)
    svc = PushService(db)

    svc._log_notification_multi(
        user_id=user.id,
        notification_type="safety_alert",
        title=card.title,
        content=card.content,
        data={"action_card_id": card.id},
        status=NotificationStatus.SENT.value,
        channels=[{"name": "ios", "status": "sent", "error": None}],
    )
    db.refresh(card)
    first_stamp = card.push_sent_at
    assert first_stamp is not None

    svc._log_notification_multi(
        user_id=user.id,
        notification_type="safety_alert",
        title=card.title,
        content=card.content,
        data={"action_card_id": card.id},
        status=NotificationStatus.SENT.value,
        channels=[{"name": "telegram", "status": "sent", "error": None}],
    )
    db.refresh(card)
    assert card.push_sent_at == first_stamp


def test_push_cross_user_isolation(db):
    """user_a 的 push 不能盖到 user_b 的卡 (防 id 串写)."""
    user_a = _make_user(db, username="alice")
    user_b = _make_user(db, username="bob")
    card_b = _make_card(db, user_b.id)
    svc = PushService(db)

    svc._log_notification_multi(
        user_id=user_a.id,
        notification_type="safety_alert",
        title="x",
        content="y",
        data={"action_card_id": card_b.id},
        status=NotificationStatus.SENT.value,
        channels=[{"name": "ios", "status": "sent", "error": None}],
    )

    db.refresh(card_b)
    assert card_b.push_sent_at is None
