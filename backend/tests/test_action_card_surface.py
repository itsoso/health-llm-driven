"""
test_action_card_surface.py —— Safety alert → action_cards 的 surface 路径.

覆盖:
- 新 alert → 新卡
- 同 rule_id 再触发 → 不新建, 仅更新 (幂等)
- 用户决策后 → 再触发, 新建 "复发" 卡
- 严重度升级 → 更新 severity
- 异常鲁棒: 内部错误不抛出 (旁路语义)
"""

from datetime import UTC, datetime

from app.agents.safety_guardian.schema import Alert, Severity
from app.models.action_card import ActionCard
from app.models.user import User
from app.services.action_card_surface import (
    surface_safety_alert,
    surface_safety_alerts,
)


def _make_user(db, username="surface_user"):
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


def _make_alert(
    rule_id="vitals.hr_spike",
    severity=Severity.HIGH,
    title="心率异常",
    message="静息心率持续 > 100bpm",
):
    return Alert(
        rule_id=rule_id,
        category="vitals",
        severity=severity,
        title=title,
        message=message,
    )


def test_surface_single_alert_creates_card(db):
    user = _make_user(db)
    alert = _make_alert()

    cid = surface_safety_alert(db, user.id, alert)
    assert cid is not None

    card = db.query(ActionCard).get(cid)
    assert card.user_id == user.id
    assert card.card_type == "alert"
    assert card.source_type == "safety_alert"
    assert card.source_id == "vitals.hr_spike"
    assert card.severity == "high"
    assert card.title == "心率异常"
    assert card.content == "静息心率持续 > 100bpm"
    assert card.user_decision is None
    assert card.status == "active"


def test_surface_same_rule_is_idempotent(db):
    """同 rule_id 再触发, 且用户未决策 → 不新建, 仅更新."""
    user = _make_user(db, username="idempotent_user")
    alert = _make_alert()

    cid1 = surface_safety_alert(db, user.id, alert)
    cid2 = surface_safety_alert(db, user.id, alert)

    assert cid1 == cid2
    count = (
        db.query(ActionCard)
        .filter(ActionCard.user_id == user.id, ActionCard.source_type == "safety_alert")
        .count()
    )
    assert count == 1


def test_surface_updates_severity_on_escalation(db):
    """规则重新评估出更高 severity → 更新而非新建."""
    user = _make_user(db, username="escalation_user")
    alert_medium = _make_alert(severity=Severity.MEDIUM)
    alert_critical = _make_alert(severity=Severity.CRITICAL)

    cid1 = surface_safety_alert(db, user.id, alert_medium)
    cid2 = surface_safety_alert(db, user.id, alert_critical)

    assert cid1 == cid2
    card = db.query(ActionCard).get(cid1)
    assert card.severity == "critical"


def test_surface_after_user_decision_creates_new_card(db):
    """用户决策过的卡 → 同 rule 再触发, 新建复发卡."""
    user = _make_user(db, username="recurrence_user")
    alert = _make_alert()

    cid1 = surface_safety_alert(db, user.id, alert)

    # 用户标为误报
    card1 = db.query(ActionCard).get(cid1)
    card1.user_decision = "false_positive"
    card1.decided_at = datetime.now(UTC)
    db.commit()

    # 同规则再次触发
    cid2 = surface_safety_alert(db, user.id, alert)

    assert cid2 != cid1
    total = (
        db.query(ActionCard)
        .filter(ActionCard.user_id == user.id, ActionCard.source_type == "safety_alert")
        .count()
    )
    assert total == 2


def test_surface_batch_writes_all(db):
    user = _make_user(db, username="batch_user")
    alerts = [
        _make_alert(rule_id="vitals.hr_spike", severity=Severity.HIGH),
        _make_alert(rule_id="labs.ldl_high", severity=Severity.MEDIUM, title="LDL偏高"),
        _make_alert(rule_id="ddi.warfarin_nsaid", severity=Severity.CRITICAL, title="药物冲突"),
    ]

    ids = surface_safety_alerts(db, user.id, alerts)
    assert len(ids) == 3

    cards = (
        db.query(ActionCard)
        .filter(ActionCard.user_id == user.id, ActionCard.source_type == "safety_alert")
        .all()
    )
    severities = sorted(c.severity for c in cards)
    assert severities == ["critical", "high", "medium"]


def test_reconcile_archives_stale_managed_safety_card(db):
    user = _make_user(db, username="archive_stale_acwr")
    stale_id = surface_safety_alert(
        db,
        user.id,
        _make_alert(rule_id="training.acwr_overload", title="训练负荷过载"),
    )
    unrelated_id = surface_safety_alert(
        db,
        user.id,
        _make_alert(rule_id="vitals.hr_spike"),
    )

    surface_safety_alerts(
        db,
        user.id,
        [],
        reconcile_rule_ids={
            "training.acwr_overload",
            "training.acwr_undertraining",
        },
    )

    stale = db.query(ActionCard).get(stale_id)
    unrelated = db.query(ActionCard).get(unrelated_id)
    assert stale.status == "archived"
    assert stale.is_visible is False
    assert unrelated.status == "active"
    assert unrelated.is_visible is True


def test_reappearing_managed_alert_reactivates_undecided_card(db):
    user = _make_user(db, username="reactivate_acwr")
    alert = _make_alert(
        rule_id="training.acwr_overload",
        title="训练负荷过载",
    )
    cid = surface_safety_alert(db, user.id, alert)

    surface_safety_alerts(
        db,
        user.id,
        [],
        reconcile_rule_ids={"training.acwr_overload"},
    )
    assert db.query(ActionCard).get(cid).status == "archived"

    same_id = surface_safety_alert(db, user.id, alert)

    card = db.query(ActionCard).get(cid)
    assert same_id == cid
    assert card.status == "active"
    assert card.is_visible is True


def test_surface_swallows_exceptions(db):
    """旁路语义: 内部异常不应该抛到调用方."""
    user = _make_user(db, username="robust_user")

    class FakeAlert:
        rule_id = "bogus"
        category = "vitals"
        severity = "not-an-enum"  # 会在 _SEVERITY_TO_LABEL 取不到, 但不该抛
        title = "x"
        message = "y"

    # 不抛异常
    result = surface_safety_alert(db, user.id, FakeAlert())
    # 可能成功 (fallback to 'info') 或失败返回 None, 都不抛
    assert result is None or isinstance(result, int)
