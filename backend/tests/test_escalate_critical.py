"""test_escalate_critical —— Critical 告警 24h 未决策升级再推 (P1-7)."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest

from app.models.action_card import ActionCard
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
