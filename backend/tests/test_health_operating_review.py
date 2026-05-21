"""Health Operating Loop 7/30/90 day review tests."""

from datetime import date, timedelta

from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import GarminData
from app.models.intervention_event import InterventionEvent
from app.models.waist import WaistRecord
from app.models.weight import WeightRecord
from tests.conftest import create_authenticated_user


def test_daily_plan_review_summarizes_events_and_metric_changes(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    today = date.today()

    db.add_all([
        InterventionEvent(
            user_id=user.id,
            plan_date=today - timedelta(days=5),
            action_key="movement.zone2_recovery",
            action_domain="movement",
            action_title="低强度 Zone 2",
            feedback_status="completed",
            source="daily_plan",
            action_snapshot={"verification_metric": "sleep_score"},
        ),
        InterventionEvent(
            user_id=user.id,
            plan_date=today - timedelta(days=2),
            action_key="sleep.dinner_cutoff",
            action_domain="sleep",
            action_title="睡前 3 小时停止正餐",
            feedback_status="skipped",
            source="daily_plan",
            action_snapshot={},
        ),
        WeightRecord(user_id=user.id, record_date=today - timedelta(days=6), weight=82.0),
        WeightRecord(user_id=user.id, record_date=today, weight=80.8),
        WaistRecord(user_id=user.id, record_date=today - timedelta(days=6), waist_cm=96.0),
        WaistRecord(user_id=user.id, record_date=today, waist_cm=94.5),
        BloodPressureRecord(user_id=user.id, record_date=today - timedelta(days=6), systolic=138, diastolic=88),
        BloodPressureRecord(user_id=user.id, record_date=today, systolic=130, diastolic=82),
        GarminData(user_id=user.id, record_date=today - timedelta(days=6), sleep_score=62, hrv=35),
        GarminData(user_id=user.id, record_date=today, sleep_score=76, hrv=42),
    ])
    db.commit()

    resp = client.get("/api/v1/daily-plan/review?window_days=7", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 7
    assert body["execution"]["total_events"] == 2
    assert body["execution"]["by_status"]["completed"] == 1
    assert body["execution"]["by_status"]["skipped"] == 1
    assert body["execution"]["completion_rate"] == 0.5
    assert body["execution"]["by_domain"]["movement"] == 1
    assert body["metrics"]["weight"]["delta"] == -1.2
    assert body["metrics"]["waist_cm"]["delta"] == -1.5
    assert body["metrics"]["systolic_bp"]["delta"] == -8
    assert body["metrics"]["sleep_score"]["delta"] == 14
    assert body["metrics"]["hrv"]["delta"] == 7
    assert "movement.zone2_recovery" in body["completed_action_keys"]
    assert body["action_effects"] == [{
        "action_key": "movement.zone2_recovery",
        "action_title": "低强度 Zone 2",
        "metric": "sleep_score",
        "metric_delta": 14,
        "direction": "improved",
        "confidence": "medium",
        "attribution": "temporal_association_not_causation",
    }]


def test_daily_plan_review_is_user_scoped(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    today = date.today()
    other_user, _ = create_authenticated_user(db)

    db.add_all([
        InterventionEvent(
            user_id=other_user.id,
            plan_date=today,
            action_key="movement.other",
            action_domain="movement",
            action_title="其他用户行动",
            feedback_status="completed",
            source="daily_plan",
            action_snapshot={},
        ),
        WeightRecord(user_id=other_user.id, record_date=today, weight=70.0),
        WeightRecord(user_id=user.id, record_date=today, weight=80.0),
    ])
    db.commit()

    resp = client.get("/api/v1/daily-plan/review?window_days=7", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["execution"]["total_events"] == 0
    assert body["metrics"]["weight"]["current"] == 80.0
    assert "movement.other" not in body["completed_action_keys"]


def test_daily_plan_review_rejects_unsupported_window(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.get("/api/v1/daily-plan/review?window_days=14", headers=headers)

    assert resp.status_code == 422
