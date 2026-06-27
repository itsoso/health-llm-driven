"""Health Runtime governance controls for source quality and derived predictions."""

from datetime import date, timedelta

from tests.conftest import create_authenticated_user


def test_source_quality_and_preference_are_user_scoped(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    other_user, _ = create_authenticated_user(db)

    resp = client.post(
        "/api/v1/health-runtime-governance/source-quality",
        headers=headers,
        json={
            "source_kind": "wearable",
            "source_id": "garmin",
            "metric": "sleep_score",
            "quality_score": 0.82,
            "confidence": "medium",
            "freshness_seconds": 3600,
            "status": "usable",
            "reason": "recent sync with no conflict",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["source_id"] == "garmin"

    pref_resp = client.post(
        "/api/v1/health-runtime-governance/source-preferences",
        headers=headers,
        json={
            "metric": "sleep_score",
            "preferred_source_kind": "wearable",
            "preferred_source_id": "garmin",
            "scope": "recovery_capacity",
            "reason": "nightly sleep source",
        },
    )
    assert pref_resp.status_code == 200
    assert pref_resp.json()["preferred_source_id"] == "garmin"

    from app.services.health_runtime_governance import list_governance_summary

    other_summary = list_governance_summary(db, other_user.id)
    assert other_summary["source_quality"] == []
    assert other_summary["source_preferences"] == []

    summary_resp = client.get("/api/v1/health-runtime-governance/me", headers=headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["source_quality"][0]["metric"] == "sleep_score"
    assert summary["source_preferences"][0]["metric"] == "sleep_score"


def test_paused_prediction_category_filters_personal_predictions(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

    cycle = InterventionCycle(
        user_id=user.id,
        cycle_type="metabolic_90d",
        status="active",
        start_date=date.today() - timedelta(days=7),
        planned_end_date=date.today() + timedelta(days=21),
    )
    db.add(cycle)
    db.flush()
    db.add(OutcomeMetric(
        cycle_id=cycle.id,
        metric_code="weight",
        unit="kg",
        baseline_value=82.0,
        latest_value=79.0,
        delta=-3.0,
        direction="down",
    ))
    db.commit()

    before = client.get("/api/v1/personal-models/predictions", headers=headers)
    assert before.status_code == 200
    assert before.json()["predictions"]

    control_resp = client.post(
        "/api/v1/health-runtime-governance/controls",
        headers=headers,
        json={
            "control_type": "prediction_category",
            "target_key": "metabolic_health",
            "status": "paused",
            "reason": "user wants fewer metabolic predictions",
        },
    )
    assert control_resp.status_code == 200
    assert control_resp.json()["status"] == "paused"

    after = client.get("/api/v1/personal-models/predictions", headers=headers)
    assert after.status_code == 200
    assert after.json()["predictions"] == []
