"""PersonalPrediction contract tests."""

from datetime import date, timedelta


def _make_active_cycle(db, user_id, *, metric_code: str = "weight", unit: str = "kg"):
    from app.models.intervention_cycle import InterventionCycle, OutcomeMetric

    cycle = InterventionCycle(
        user_id=user_id,
        cycle_type="metabolic_90d",
        status="active",
        start_date=date.today() - timedelta(days=21),
        planned_end_date=date.today() + timedelta(days=49),
    )
    db.add(cycle)
    db.flush()
    db.add(OutcomeMetric(
        cycle_id=cycle.id,
        metric_code=metric_code,
        unit=unit,
        baseline_value=82.0,
        latest_value=79.0,
        delta=-3.0,
        direction="down",
    ))
    db.commit()
    db.refresh(cycle)
    return cycle


def test_personal_prediction_contract_from_active_intervention_cycle(db, auth_user_and_headers):
    from app.services.personal_models.personal_prediction import build_personal_predictions

    user, _ = auth_user_and_headers
    cycle = _make_active_cycle(db, user.id)

    predictions = build_personal_predictions(db, user.id)

    assert len(predictions) == 1
    prediction = predictions[0]
    assert prediction["id"] == f"personal_prediction:cycle:{cycle.id}:weight"
    assert prediction["prediction_type"] == "intervention_cycle_projection"
    assert prediction["metric"] == "weight"
    assert prediction["domain"] == "metabolic_health"
    assert prediction["horizon_days"] == 49
    assert prediction["baseline"] == 79.0
    assert prediction["expected_signal"]["direction"] == "down"
    assert prediction["expected_signal"]["expected_delta"] < 0
    assert prediction["source_model"] == "phase1-hbayes-v1"
    assert prediction["model_version"] == "personal_prediction_v1"
    assert prediction["confidence"] in {"low", "medium", "high"}
    assert prediction["uncertainty"]["level"] in {"low", "medium", "high"}
    assert "不替代医生诊断" in prediction["claim_boundary"]


def test_personal_predictions_endpoint_shape(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _make_active_cycle(db, user.id)

    resp = client.get("/api/v1/personal-models/predictions", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["generated_by"] == "personal_prediction_v1"
    assert len(body["predictions"]) == 1
    assert body["predictions"][0]["metric"] == "weight"
    assert body["predictions"][0]["uncertainty"]["drivers"]


def test_daily_plan_actions_attach_matching_personal_prediction_context(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    _make_active_cycle(db, user.id, metric_code="waist_cm", unit="cm")

    from app.services.daily_operating_plan import build_daily_operating_plan

    plan = build_daily_operating_plan(db, user.id)

    measurement = next(action for action in plan["actions"] if action["action_key"] == "measurement.weight_waist_morning")
    prediction = measurement["personal_prediction_context"]
    assert prediction["id"].startswith("personal_prediction:cycle:")
    assert prediction["metric"] == "waist_cm"
    assert prediction["model_version"] == "personal_prediction_v1"
    assert prediction["expected_signal"]["direction"] == "down"
