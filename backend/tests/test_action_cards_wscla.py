"""
test_action_cards_wscla.py —— WSCLA 生命周期字段 (Phase 0 · W1 定基线).

覆盖:
- 新字段默认 NULL (不破坏历史卡)
- user_decision 四种合法值可落库
- severity 合法值可落库
- outcome 合法值可落库
- 通知生命周期四时间戳可独立写入
- CHECK 约束拒绝非法值 (PG 专属, SQLite 不强制 CHECK, 跳过)
- WSCLA 聚合 SQL 逻辑在 ORM 层可计算
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.action_card import ActionCard
from app.models.user import User


def _make_user(db, username="wscla_user"):
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


def test_new_wscla_fields_default_none(db):
    user = _make_user(db)
    card = ActionCard(user_id=user.id, title="普通计划", content="内容")
    db.add(card)
    db.commit()
    db.refresh(card)

    # 10 个新字段默认 NULL, 不破坏历史卡
    assert card.seen_at is None
    assert card.push_sent_at is None
    assert card.push_delivered_at is None
    assert card.push_clicked_at is None
    assert card.user_decision is None
    assert card.decided_at is None
    assert card.decision_reason is None
    assert card.severity is None
    assert card.outcome is None
    assert card.effect_size is None


@pytest.mark.parametrize(
    "decision",
    ["accepted", "adjusted", "declined", "dismissed", "false_positive"],
)
def test_user_decision_accepts_all_legal_values(db, decision):
    user = _make_user(db, username=f"dec_{decision}")
    now = datetime.now(timezone.utc)
    card = ActionCard(
        user_id=user.id,
        title="test",
        content="c",
        user_decision=decision,
        decided_at=now,
        decision_reason="test reason",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    assert card.user_decision == decision
    assert card.decided_at is not None


@pytest.mark.parametrize(
    "severity",
    ["critical", "high", "medium", "low", "info"],
)
def test_severity_accepts_all_legal_values(db, severity):
    user = _make_user(db, username=f"sev_{severity}")
    card = ActionCard(
        user_id=user.id,
        title="alert",
        content="c",
        card_type="alert",
        source_type="safety_alert",
        severity=severity,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    assert card.severity == severity


@pytest.mark.parametrize(
    "outcome",
    ["improved", "unchanged", "worsened", "inconclusive"],
)
def test_outcome_accepts_all_legal_values(db, outcome):
    user = _make_user(db, username=f"out_{outcome}")
    card = ActionCard(
        user_id=user.id,
        title="test",
        content="c",
        outcome=outcome,
        effect_size=0.42,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    assert card.outcome == outcome
    assert card.effect_size == pytest.approx(0.42)


def test_push_lifecycle_four_timestamps(db):
    """Push 发送 → 送达 → 点击 → 看到: 四个时间戳正交可独立设置."""
    user = _make_user(db, username="push_user")
    now = datetime.now(timezone.utc)

    card = ActionCard(
        user_id=user.id,
        title="推送卡",
        content="c",
        push_sent_at=now,
        push_delivered_at=now + timedelta(seconds=1),
        push_clicked_at=now + timedelta(seconds=30),
        seen_at=now + timedelta(seconds=30),
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    assert card.push_sent_at is not None
    assert card.push_delivered_at > card.push_sent_at
    assert card.push_clicked_at > card.push_delivered_at
    assert card.seen_at is not None


def test_wscla_aggregation_only_counts_full_closed_loop(db):
    """WSCLA 口径: 本周 **闭环完成** (graded_at 在本周内) 且 outcome 是 improved/unchanged.
    闭环时间用 graded_at 而非 created_at, 因为建议可能 28 天前发出, 本周才验证完成."""
    user = _make_user(db, username="wscla_agg")
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    in_week = week_start + timedelta(minutes=1)
    last_week = week_start - timedelta(days=3)

    # 1. 本周完整闭环 improved → 计入
    db.add(
        ActionCard(
            user_id=user.id,
            title="a",
            content="c",
            user_decision="accepted",
            decided_at=last_week,
            completed_at=now - timedelta(days=1),
            graded_at=now,
            outcome="improved",
        )
    )
    # 2. 本周完整闭环 unchanged → 计入
    db.add(
        ActionCard(
            user_id=user.id,
            title="b",
            content="c",
            user_decision="accepted",
            decided_at=last_week,
            completed_at=now - timedelta(days=1),
            graded_at=in_week,
            outcome="unchanged",
        )
    )
    # 3. 本周 worsened → 不计入 (不是 "safe" closed loop)
    db.add(
        ActionCard(
            user_id=user.id,
            title="c",
            content="c",
            user_decision="accepted",
            completed_at=now - timedelta(days=1),
            graded_at=now,
            outcome="worsened",
        )
    )
    # 4. 本周被拒绝 → 不计入
    db.add(
        ActionCard(
            user_id=user.id,
            title="d",
            content="c",
            user_decision="declined",
            decided_at=now - timedelta(days=1),
        )
    )
    # 5. 接受但未验证 → 不计入
    db.add(
        ActionCard(
            user_id=user.id,
            title="e",
            content="c",
            user_decision="accepted",
            completed_at=now,
        )
    )
    # 6. 上周已闭环 → 本周 WSCLA 不计入 (graded_at 在上周)
    db.add(
        ActionCard(
            user_id=user.id,
            title="f",
            content="c",
            user_decision="accepted",
            completed_at=last_week,
            graded_at=last_week + timedelta(hours=1),
            outcome="improved",
        )
    )
    db.commit()

    wscla = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == user.id,
            ActionCard.user_decision == "accepted",
            ActionCard.completed_at.isnot(None),
            ActionCard.graded_at >= week_start,
            ActionCard.outcome.in_(["improved", "unchanged"]),
        )
        .count()
    )

    assert wscla == 2, "只有样本 1 (improved) 和样本 2 (unchanged) 应该计入"


def test_safety_alert_shape_in_action_cards(db):
    """Safety 告警纳入 action_cards: card_type='alert' + source_type='safety_alert' + severity."""
    user = _make_user(db, username="safety_user")

    card = ActionCard(
        user_id=user.id,
        title="心率异常 02:13",
        content="心率 > 120 持续 8 分钟, 确认是否就医",
        card_type="alert",
        source_type="safety_alert",
        source_id="vitals.hr_spike",
        severity="high",
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    # 用户反馈 false_positive
    card.user_decision = "false_positive"
    card.decided_at = datetime.now(timezone.utc)
    card.decision_reason = "刚跑完步, 正常升高"
    db.commit()
    db.refresh(card)

    assert card.card_type == "alert"
    assert card.source_type == "safety_alert"
    assert card.severity == "high"
    assert card.user_decision == "false_positive"


def test_status_and_user_decision_are_orthogonal(db):
    """status 是系统视角 (active/completed/archived),
    user_decision 是用户意图 (accepted/declined/...), 二者正交.
    一张卡可以 status='completed' 但 user_decision='declined' (例: 到期自动归档, 用户曾拒绝)."""
    user = _make_user(db, username="orthogonal_user")

    card = ActionCard(
        user_id=user.id,
        title="test",
        content="c",
        status="archived",
        user_decision="declined",
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    assert card.status == "archived"
    assert card.user_decision == "declined"
