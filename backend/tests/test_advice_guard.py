from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.advice_ledger import AdviceLedger
from app.services.advice_guard import (
    AdviceCandidate,
    AdviceGuard,
    AdviceGuardError,
    guard_and_record_advice,
    normalize_advice_key,
)
from app.services.daily_operating_plan import _guard_plan_actions
from app.services.notification.push_service import _advice_candidate_from_push


def _candidate(**overrides) -> AdviceCandidate:
    base = {
        "user_id": 3,
        "source": "daily_plan",
        "source_id": "plan:2026-05-16",
        "domain": "movement",
        "title": "降低跑步强度，改为 Zone 2 恢复",
        "body": "训练准备度偏低时不堆高强度。",
        "metric_key": "training_load",
        "target_value": "reduce_intensity",
        "evidence_tier": "wearable_proxy",
        "confidence": "medium",
        "claim_boundary": "用于恢复管理，不替代医生诊断。",
        "valid_for_date": date(2026, 5, 16),
    }
    base.update(overrides)
    return AdviceCandidate(**base)


def test_normalize_advice_key_is_stable_for_duplicate_content():
    first = normalize_advice_key(
        user_id=3,
        domain="movement",
        metric_key="training_load",
        target_value="reduce_intensity",
        valid_for_date=date(2026, 5, 16),
    )
    second = normalize_advice_key(
        user_id=3,
        domain="movement",
        metric_key="training_load",
        target_value="reduce_intensity",
        valid_for_date=date(2026, 5, 16),
    )

    assert first == second


def test_guard_rejects_missing_science_boundary():
    guard = AdviceGuard(existing=[])
    candidate = _candidate(claim_boundary="")

    try:
        guard.evaluate(candidate)
    except AdviceGuardError as exc:
        assert "claim_boundary" in str(exc)
    else:
        raise AssertionError("missing claim_boundary should be rejected")


def test_guard_blocks_conflicting_movement_advice():
    existing = [
        _candidate(
            source="agent",
            source_id="chat:1",
            target_value="reduce_intensity",
            title="本周先暂停跑步，保恢复",
            created_at=datetime(2026, 5, 16, 8, 0, tzinfo=timezone.utc),
        )
    ]
    guard = AdviceGuard(existing=existing)
    candidate = _candidate(
        source="push",
        source_id="push:1",
        target_value="increase_activity",
        title="长期运动不足，建议提高运动强度",
    )

    result = guard.evaluate(candidate)

    assert result.allowed is False
    assert result.reason == "conflict"
    assert result.conflicts_with_source_id == "chat:1"


def test_guard_and_record_advice_persists_blocked_conflict():
    engine = create_engine("sqlite:///:memory:")
    AdviceLedger.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    first = guard_and_record_advice(db, _candidate(source="agent", source_id="chat:1"))
    second = guard_and_record_advice(
        db,
        _candidate(
            source="push",
            source_id="push:1",
            target_value="increase_activity",
            title="长期运动不足，建议提高运动强度",
        ),
    )

    rows = db.query(AdviceLedger).order_by(AdviceLedger.id).all()
    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "conflict"
    assert [r.decision for r in rows] == ["allowed", "blocked"]
    assert rows[1].conflicts_with_id == rows[0].id


def test_push_movement_alert_is_mapped_to_advice_candidate():
    candidate = _advice_candidate_from_push(
        user_id=3,
        notification_type="health_alert",
        title="健康趋势",
        content="长期运动不足可能导致体能下降，建议关注并及时干预。",
        data={"rule_id": "trend.low_activity"},
        severity="warning",
    )

    assert candidate is not None
    assert candidate.domain == "movement"
    assert candidate.metric_key == "trend.low_activity"
    assert candidate.target_value == "increase_activity"
    assert candidate.evidence_tier == "wearable_proxy"


def test_trend_report_movement_alert_is_mapped_to_advice_candidate():
    candidate = _advice_candidate_from_push(
        user_id=3,
        notification_type="trend_report",
        title="健康趋势",
        content="长期运动不足可能导致体能下降，建议关注并及时干预。",
        data={"rule_id": "trend.low_activity"},
        severity="warning",
    )

    assert candidate is not None
    assert candidate.domain == "movement"
    assert candidate.metric_key == "trend.low_activity"
    assert candidate.target_value == "increase_activity"


def test_trend_report_push_conflicts_with_active_recovery_advice(db):
    from app.models.notification import UserNotificationSetting
    from app.models.user import User
    from app.services.notification.push_service import PushService

    user = User(
        username="trend_conflict",
        email="trend_conflict@test.local",
        name="trend_conflict",
        hashed_password="x",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserNotificationSetting(
        user_id=user.id,
        enabled=True,
        health_alert_enabled=True,
        ios_push_enabled=True,
        ios_device_token="fake-token",
        wechat_enabled=False,
    ))
    db.commit()
    guard_and_record_advice(db, _candidate(user_id=user.id, source="agent", source_id="chat:recovery"))

    import asyncio

    result = asyncio.run(PushService(db).send_notification(
        user_id=user.id,
        notification_type="trend_report",
        title="📈 健康趋势",
        content="长期运动不足可能导致体能下降，建议关注并及时干预。",
        data={"rule_id": "trend.low_activity"},
        severity="warning",
        channels=["ios_apns"],
    ))

    assert result["success"] is False
    assert result["reason"] == "advice_guard_conflict"


def test_daily_plan_guard_filters_conflicting_movement_action():
    engine = create_engine("sqlite:///:memory:")
    AdviceLedger.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    guard_and_record_advice(db, _candidate(source="agent", source_id="chat:1"))

    actions = [
        {
            "domain": "movement",
            "title": "累计 35-45 分钟中等强度活动",
            "why": "对齐每周 150 分钟中等强度活动的代谢健康目标。",
            "when": "daytime",
            "metric_key": "custom",
            "target_value": "150min_weekly",
            "evidence_tier": "strong_behavioral",
            "confidence": "high",
            "claim_boundary": "活动目标用于健康管理, 不替代医生评估。",
        },
        {
            "domain": "sleep",
            "title": "睡前 3 小时停止正餐",
            "why": "减少睡眠干扰。",
            "when": "evening",
            "metric_key": "sleep_score",
            "target_value": "trend_up",
            "evidence_tier": "strong_behavioral",
            "confidence": "medium",
            "claim_boundary": "睡眠建议不替代睡眠障碍诊断。",
        },
    ]

    filtered = _guard_plan_actions(db, user_id=3, plan_date=date(2026, 5, 16), actions=actions)

    assert [item["domain"] for item in filtered] == ["sleep"]
