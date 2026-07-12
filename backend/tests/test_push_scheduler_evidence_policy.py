from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.models.daily_health import GarminData
from app.models.user import User
from app.services.notification.push_scheduler import (
    PushScheduler,
    build_health_alert_push_data,
)


def test_health_alert_push_data_marks_safety_alert_as_supported_boundary():
    data = build_health_alert_push_data({"type": "poor_sleep"})

    assert data["alert_type"] == "poor_sleep"
    assert data["support_status"] == "safety_alert"
    assert data["unsupported"] is False
    assert data["unsupported_reason"] is None
    assert data["evidence_ref_count"] == 0
    assert data["evidence_refs"] == []
    assert data["planner_evidence_policy"]["blocked"] is False
    assert data["planner_evidence_policy"]["kept_reason"] == "safety_or_data_gap"
    assert "不替代医生" in data["claim_boundary"]


def test_health_alert_push_data_adds_rule_identity_for_dedup_and_opt_out():
    data = build_health_alert_push_data({"type": "high_stress"})

    assert data["rule_id"] == "wearable.high_stress"
    assert data["rule_source"] == "push_scheduler.wearable_threshold"
    assert data["evidence_domain"] == "recovery_stress"


@pytest.mark.asyncio
async def test_scheduler_health_alerts_respect_quiet_hours_for_non_critical(db, monkeypatch):
    """Scheduler-level alerts must not bypass the user's quiet-hours settings."""
    user = User(
        username="quiet_scheduler",
        email="quiet_scheduler@example.com",
        hashed_password="x",
        name="quiet_scheduler",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    today = date(2026, 7, 12)
    db.add(
        GarminData(
            user_id=user.id,
            record_date=today,
            data_source="garmin",
            resting_heart_rate=105,
        )
    )
    db.commit()

    monkeypatch.setattr(
        "app.utils.timezone.get_china_today",
        lambda: today,
    )

    push_service = AsyncMock()
    push_service.send_notification.return_value = {"success": False, "reason": "delayed_for_quiet_hours"}

    await PushScheduler()._check_health_alerts(db, push_service)

    push_service.send_notification.assert_awaited_once()
    kwargs = push_service.send_notification.await_args.kwargs
    assert kwargs["notification_type"] == "health_alert"
    assert kwargs["data"]["alert_type"] == "high_heart_rate"
    assert kwargs["respect_quiet_hours"] is True
    assert kwargs["severity"] == "high"
