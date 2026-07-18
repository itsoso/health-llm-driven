"""test_escalate_critical —— Critical 告警 24h 未决策升级再推 (P1-7)."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest

from app.models.action_card import ActionCard
from app.models.notification import NotificationLog, NotificationStatus
from app.models.user import User
from app.services.notification.push_service import PushService
from app.tasks.notifications import escalate_critical_unresolved


@pytest.fixture(autouse=True)
def patch_session_local(db):
    """让 task 里的 SessionLocal() 走测试用的 in-memory db.

    @contextmanager wrapper 让 'with SessionLocal() as db' 语法仍可用,
    但 __exit__ 不真关 (db fixture 已托管生命周期).
    """
    @contextmanager
    def _ctx():
        try:
            yield db
        finally:
            pass

    with patch("app.tasks.notifications_wscla.SessionLocal", new=_ctx):
        yield


def _make_user(db, username="esc_user"):
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        name=username,
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_critical_card(db, user_id, push_sent_at, **kw):
    base = dict(
        user_id=user_id,
        title="critical 告警",
        content="重要内容",
        card_type="alert",
        source_type="safety_alert",
        source_id="vitals.bp_critical",
        severity="critical",
        status="active",
        push_sent_at=push_sent_at,
    )
    base.update(kw)
    card = ActionCard(**base)
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def test_escalates_critical_pending_24h(db):
    user = _make_user(db, "esc_24h")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id, push_sent_at=now - timedelta(hours=25)
    )

    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    assert result["escalated"] >= 1
    fake_send.assert_called()
    db.refresh(card)
    meta = card.latest_assessment or {}
    assert meta.get("escalation_count") == 1
    assert meta.get("last_escalated_at") is not None


def test_does_not_escalate_recent_alert(db):
    """push_sent_at 不到 24h, 不升级."""
    user = _make_user(db, "esc_recent")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id, push_sent_at=now - timedelta(hours=10)
    )

    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    assert result["escalated"] == 0
    fake_send.assert_not_called()


def test_does_not_escalate_decided_alert(db):
    """已 decided 的告警不再升级."""
    user = _make_user(db, "esc_decided")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id,
        push_sent_at=now - timedelta(hours=30),
        user_decision="accepted",
        decided_at=now - timedelta(hours=20),
    )

    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    assert result["escalated"] == 0
    fake_send.assert_not_called()


def test_max_3_escalations(db):
    """已 escalate 3 次的不再推."""
    user = _make_user(db, "esc_max")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id,
        push_sent_at=now - timedelta(hours=72),
        latest_assessment={
            "escalation_count": 3,
            "last_escalated_at": (now - timedelta(hours=20)).isoformat(),
        },
    )

    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    assert result["escalated"] == 0
    assert result["skipped"] >= 1
    fake_send.assert_not_called()


def test_min_gap_12h_between_escalations(db):
    """两次 escalate 之间至少 12h, 否则跳过."""
    user = _make_user(db, "esc_gap")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id,
        push_sent_at=now - timedelta(hours=48),
        latest_assessment={
            "escalation_count": 1,
            "last_escalated_at": (now - timedelta(hours=2)).isoformat(),  # 2h 前刚推过
        },
    )

    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    assert result["escalated"] == 0
    assert result["skipped"] >= 1


def test_dedup_drop_does_not_burn_escalation_slot(db):
    """推送被 dedup 丢弃 → 不能消耗 escalation 名额 (AGENTS.md: 不假装成功).

    MAX_ESCALATIONS=3 是"用户真收到 3 次"的预算, 不是"尝试 3 次"。
    send_notification 返回 success=False/reason=dedup 时用户什么都没收到,
    若仍 +1 则 3 次名额会被静默烧光 → under-alarm。
    """
    user = _make_user(db, "esc_dedup")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id, push_sent_at=now - timedelta(hours=25)
    )

    fake_send = AsyncMock(return_value={"success": False, "reason": "dedup"})
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    fake_send.assert_called()
    db.refresh(card)
    meta = card.latest_assessment or {}
    assert meta.get("escalation_count", 0) == 0, "被 dedup 丢弃的推送烧掉了 escalation 名额"
    assert meta.get("last_escalated_at") is None
    assert result["escalated"] == 0, "用户没收到推送, 不能报 escalated"


def test_quiet_hours_delay_waits_for_actual_delivery_before_counting(db):
    """仅入延迟队列不能提前消耗升级次数，flush 真正发送成功后才记账。"""
    user = _make_user(db, "esc_delayed")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id, push_sent_at=now - timedelta(hours=25)
    )

    fake_send = AsyncMock(return_value={
        "success": False,
        "reason": "delayed_for_quiet_hours",
        "scheduled_at": now.isoformat(),
    })
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    db.refresh(card)
    meta = card.latest_assessment or {}
    assert meta.get("escalation_count", 0) == 0
    assert datetime.fromisoformat(meta["escalation_pending_delivery_at"]).tzinfo is not None
    assert result["escalated"] == 0
    assert result["pending"] == 1


def test_sent_delayed_escalation_is_accounted_once_after_flush(db):
    """延迟推送状态变为 SENT 后，才为对应卡片记一次升级，重复 flush 不得重复记账。"""
    from app.tasks.notifications_wscla import _account_sent_delayed_escalations

    user = _make_user(db, "esc_delayed_sent")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id, push_sent_at=now - timedelta(hours=25),
        latest_assessment={
            "escalation_count": 0,
            "escalation_pending_delivery_at": (now - timedelta(minutes=5)).isoformat(),
            "escalation_pending_expected_count": 1,
        },
    )
    log = NotificationLog(
        user_id=user.id,
        notification_type="health_alert",
        channel="ios_apns",
        title="critical 告警",
        content="x",
        status=NotificationStatus.SENT.value,
        sent_at=now,
        data={
            "rule_id": card.source_id,
            "escalation_action_card_id": card.id,
            "escalation_expected_count": 1,
        },
    )
    db.add(log)
    db.commit()

    assert _account_sent_delayed_escalations(db, now) == 1
    db.refresh(card)
    db.refresh(log)
    assert (card.latest_assessment or {}).get("escalation_count") == 1
    assert (card.latest_assessment or {}).get("last_escalated_at") == now.isoformat()
    assert "escalation_pending_delivery_at" not in (card.latest_assessment or {})
    assert (log.data or {}).get("escalation_delivery_accounted") is True

    assert _account_sent_delayed_escalations(db, now) == 0
    db.refresh(card)
    assert (card.latest_assessment or {}).get("escalation_count") == 1


def test_sent_delayed_escalation_never_accounts_another_users_card(db):
    """日志中的 card id 必须同时属于该推送用户，不能跨用户记账。"""
    from app.tasks.notifications_wscla import _account_sent_delayed_escalations

    sender = _make_user(db, "esc_sender")
    owner = _make_user(db, "esc_owner")
    now = datetime.now(timezone.utc)
    owner_card = _make_critical_card(
        db, owner.id, push_sent_at=now - timedelta(hours=25),
    )
    log = NotificationLog(
        user_id=sender.id,
        notification_type="health_alert",
        channel="ios_apns",
        title="critical 告警",
        content="x",
        status=NotificationStatus.SENT.value,
        sent_at=now,
        data={
            "rule_id": owner_card.source_id,
            "escalation_action_card_id": owner_card.id,
            "escalation_expected_count": 1,
        },
    )
    db.add(log)
    db.commit()

    assert _account_sent_delayed_escalations(db, now) == 0
    db.refresh(owner_card)
    db.refresh(log)
    assert (owner_card.latest_assessment or {}).get("escalation_count", 0) == 0
    assert (log.data or {}).get("escalation_delivery_accounted") is True


def test_sent_delayed_escalation_query_locks_rows_on_postgres(db):
    """并发 flush 必须以 SKIP LOCKED 串行化同一条 SENT escalation log 的记账。"""
    from sqlalchemy.dialects import postgresql

    from app.tasks.notifications_wscla import _sent_escalation_logs_for_update

    statement = _sent_escalation_logs_for_update(db).statement
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql


def test_permanently_undelivered_escalation_stops_after_bounded_retries(db):
    """无渠道等永久失败只退避有限次，不能每小时无限重试。"""
    from app.tasks import notifications_wscla

    user = _make_user(db, "esc_bounded")
    base = datetime.now(timezone.utc).replace(microsecond=0)
    card = _make_critical_card(
        db, user.id, push_sent_at=base - timedelta(hours=25),
    )
    fake_send = AsyncMock(return_value={"success": False, "reason": "no_channels"})

    with patch.object(PushService, "send_notification", new=fake_send), \
            patch.object(
                notifications_wscla,
                "get_china_now",
                side_effect=[base, base + timedelta(hours=1), base + timedelta(hours=3), base + timedelta(hours=7)],
            ):
        first = escalate_critical_unresolved()
        second = escalate_critical_unresolved()
        third = escalate_critical_unresolved()
        fourth = escalate_critical_unresolved()

    assert [first["undelivered"], second["undelivered"], third["undelivered"]] == [1, 1, 1]
    assert fourth["undelivered"] == 0
    assert fake_send.await_count == 3
    db.refresh(card)
    meta = card.latest_assessment or {}
    assert meta.get("escalation_delivery_blocked_at") == (base + timedelta(hours=3)).isoformat()


def test_dedup_retry_waits_for_critical_dedup_window(db):
    """dedup 后不按小时空转，等当前 critical 的 3h 去重窗口滑开再试。"""
    from app.tasks import notifications_wscla

    user = _make_user(db, "esc_dedup_backoff")
    base = datetime.now(timezone.utc).replace(microsecond=0)
    _make_critical_card(db, user.id, push_sent_at=base - timedelta(hours=25))
    fake_send = AsyncMock(side_effect=[
        {"success": False, "reason": "dedup"},
        {"success": True},
    ])

    with patch.object(PushService, "send_notification", new=fake_send), \
            patch.object(
                notifications_wscla,
                "get_china_now",
                side_effect=[base, base + timedelta(hours=2), base + timedelta(hours=3)],
            ):
        first = escalate_critical_unresolved()
        second = escalate_critical_unresolved()
        third = escalate_critical_unresolved()

    assert first["undelivered"] == 1
    assert second["undelivered"] == 0
    assert second["skipped"] == 1
    assert third["escalated"] == 1
    assert fake_send.await_count == 2


def test_gatekeeper_drop_does_not_burn_escalation_slot(db):
    """触达预算/AdviceGuard 拦截同样是"用户没收到" → 不烧名额."""
    user = _make_user(db, "esc_gate")
    now = datetime.now(timezone.utc)
    card = _make_critical_card(
        db, user.id, push_sent_at=now - timedelta(hours=25)
    )

    fake_send = AsyncMock(return_value={"success": False, "reason": "gatekeeper_budget"})
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    db.refresh(card)
    meta = card.latest_assessment or {}
    assert meta.get("escalation_count", 0) == 0
    assert result["escalated"] == 0


def test_only_critical_severity(db):
    """High/Medium 不升级, 只有 critical 才升级."""
    user = _make_user(db, "esc_severity")
    now = datetime.now(timezone.utc)
    _make_critical_card(
        db, user.id,
        push_sent_at=now - timedelta(hours=30),
        severity="high",
    )
    _make_critical_card(
        db, user.id,
        push_sent_at=now - timedelta(hours=30),
        severity="medium",
    )

    fake_send = AsyncMock(return_value={"success": True})
    with patch.object(PushService, "send_notification", new=fake_send):
        result = escalate_critical_unresolved()

    assert result["escalated"] == 0
    fake_send.assert_not_called()
