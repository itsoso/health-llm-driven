from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone


def test_build_daily_plan_acute_rest_suppresses_movement_interventions(db):
    """急性不适需要休息时，应压制训练/跑步类 intervention，避免和恢复模式冲突。"""
    from app.models.action_card import ActionCard
    from app.models.illness import IllnessEpisode
    from app.models.symptom_entry import SymptomEntry
    from app.models.user import User
    from app.services.daily_operating_plan import build_daily_operating_plan

    user = User(
        username=f"dp_{uuid.uuid4().hex[:6]}",
        email=f"dp_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="Daily Plan User",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(IllnessEpisode(
        user_id=user.id,
        name="感冒",
        start_date=date.today() - timedelta(days=1),
        status="active",
        severity=5,
    ))
    db.add(SymptomEntry(
        user_id=user.id,
        occurred_at=datetime.now(timezone.utc),
        body_part="respiratory",
        description="咳嗽，嗓子疼，鼻塞",
        severity=4,
        source="voice",
    ))
    db.add(ActionCard(
        user_id=user.id,
        title="跑步训练计划（每日 5km）",
        content="测试：运动类干预卡片在急性期不应被展示。",
        status="active",
        user_decision="accepted",
        priority=10,
        metric_key="custom",
        target_value="5km_daily",
        evidence_level="high",
    ))
    db.commit()

    payload = build_daily_operating_plan(db, user.id, plan_date=date.today())

    assert any(a.get("action_key") == "movement.pause_training_acute" for a in payload["actions"])
    assert not any(a.get("action_key", "").startswith("intervention.card.") for a in payload["actions"])

    notes = payload["state_summary"].get("arbitration_notes")
    assert isinstance(notes, list)
    assert any(n.get("reason") == "acute_rest_from_training" for n in notes)


def test_build_daily_plan_acute_rest_suppresses_fitness_synonyms(db):
    """急性不适需要休息时，"健身/运动" 等同义词也应被压制，避免漏网导致冲突。"""
    from app.models.action_card import ActionCard
    from app.models.illness import IllnessEpisode
    from app.models.symptom_entry import SymptomEntry
    from app.models.user import User
    from app.services.daily_operating_plan import build_daily_operating_plan

    user = User(
        username=f"dp_{uuid.uuid4().hex[:6]}",
        email=f"dp_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="Daily Plan User",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(IllnessEpisode(
        user_id=user.id,
        name="感冒",
        start_date=date.today() - timedelta(days=1),
        status="active",
        severity=5,
    ))
    db.add(SymptomEntry(
        user_id=user.id,
        occurred_at=datetime.now(timezone.utc),
        body_part="respiratory",
        description="咳嗽，嗓子疼，鼻塞",
        severity=4,
        source="voice",
    ))

    card = ActionCard(
        user_id=user.id,
        title="健身计划（每日 30 分钟）",
        content="测试：健身/运动同义词在急性期也不应被展示。",
        status="active",
        user_decision="accepted",
        priority=10,
        metric_key="custom",
        target_value="fitness_30m_daily",
        evidence_level="high",
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    payload = build_daily_operating_plan(db, user.id, plan_date=date.today())

    assert any(a.get("action_key") == "movement.pause_training_acute" for a in payload["actions"])
    assert not any(a.get("action_key") == f"intervention.card.{card.id}" for a in payload["actions"])

    notes = payload["state_summary"].get("arbitration_notes")
    assert isinstance(notes, list)
    assert any(
        n.get("reason") == "acute_rest_from_training"
        and f"intervention.card.{card.id}" in (n.get("suppressed_action_keys") or [])
        for n in notes
    )
