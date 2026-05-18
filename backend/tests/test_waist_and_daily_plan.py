"""Waist records + DailyOperatingPlan Phase 0 contract tests."""

from datetime import date, timedelta


def test_create_and_list_my_waist_records(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    create = client.post(
        "/api/v1/waist/records",
        headers=headers,
        json={
            "record_date": date.today().isoformat(),
            "waist_cm": 88.5,
            "source": "manual",
            "notes": "morning",
        },
    )

    assert create.status_code == 200
    body = create.json()
    assert body["waist_cm"] == 88.5
    assert body["source"] == "manual"

    listed = client.get("/api/v1/waist/records/me", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["waist_cm"] == 88.5


def test_waist_record_upserts_same_day(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    payload = {"record_date": date.today().isoformat(), "waist_cm": 90.0}

    first = client.post("/api/v1/waist/records", headers=headers, json=payload)
    second = client.post(
        "/api/v1/waist/records",
        headers=headers,
        json={**payload, "waist_cm": 89.0},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["waist_cm"] == 89.0


def test_waist_record_update_is_scoped_to_current_user(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    from app.models.user import User
    from app.models.waist import WaistRecord

    other_user = User(
        username="waist_other_user",
        email="waist_other@example.com",
        hashed_password="x",
        name="Other",
        is_active=True,
        is_approved=True,
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)
    other_record = WaistRecord(
        user_id=other_user.id,
        record_date=date.today(),
        waist_cm=93.0,
    )
    db.add(other_record)
    db.commit()
    db.refresh(other_record)

    resp = client.put(
        f"/api/v1/waist/records/{other_record.id}",
        headers=headers,
        json={"waist_cm": 88.0},
    )

    assert resp.status_code == 404
    db.refresh(other_record)
    assert other_record.waist_cm == 93.0


def test_twin_includes_latest_waist_and_central_obesity(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    from app.models.waist import WaistRecord

    db.add(WaistRecord(
        user_id=user.id,
        record_date=date.today(),
        waist_cm=91.0,
        source="manual",
    ))
    db.commit()

    resp = client.get("/api/v1/twin/me?fresh=true", headers=headers)

    assert resp.status_code == 200
    body = resp.json()["body_composition"]
    assert body["waist_cm"] == 91.0
    assert body["central_obesity_flag"] is True
    assert "waist" in resp.json()["meta"]["data_sources"]


def test_daily_operating_plan_me_returns_metabolic_actions(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    from app.models.action_card import ActionCard
    from app.models.blood_pressure import BloodPressureRecord
    from app.models.waist import WaistRecord
    from app.models.weight import WeightRecord

    db.add(WeightRecord(user_id=user.id, record_date=date.today(), weight=82.0, bmi=27.2))
    db.add(WaistRecord(user_id=user.id, record_date=date.today(), waist_cm=92.0))
    db.add(BloodPressureRecord(
        user_id=user.id,
        record_date=date.today(),
        systolic=132,
        diastolic=86,
    ))
    db.add(ActionCard(
        user_id=user.id,
        title="7 天提前晚餐",
        content="19:00 前完成晚餐, 观察睡眠和体重。",
        status="active",
        user_decision="accepted",
        metric_key="weight",
        baseline_value="82",
        target_value="<81.5",
        check_back_date=date.today() + timedelta(days=7),
    ))
    db.commit()

    resp = client.get("/api/v1/daily-plan/me", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_date"] == date.today().isoformat()
    assert body["primary_goal"] == "metabolic_health"
    assert body["state_summary"]["waist_cm"] == 92.0
    assert body["state_summary"]["blood_pressure"] == "132/86"
    assert len(body["actions"]) >= 3
    assert any(action["domain"] == "measurement" and "腰围" in action["title"] for action in body["actions"])
    assert any(action["domain"] == "nutrition" for action in body["actions"])
    assert all(action["evidence_tier"] for action in body["actions"])
    assert all(action["confidence"] in {"high", "medium", "low"} for action in body["actions"])
    assert all("不替代" in action["claim_boundary"] for action in body["actions"])
    measurement = next(action for action in body["actions"] if action["domain"] == "measurement")
    assert measurement["evidence_tier"] == "clinical_guideline"
    assert measurement["confidence"] == "high"
    assert body["verification"]["metrics"]


def test_daily_operating_plan_pauses_movement_when_user_has_active_cold(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    from app.models.illness import IllnessEpisode

    db.add(IllnessEpisode(
        user_id=user.id,
        name="感冒",
        start_date=date.today(),
        status="active",
        severity=4,
    ))
    db.commit()

    resp = client.get("/api/v1/daily-plan/me", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    movement_actions = [action for action in body["actions"] if action["domain"] == "movement"]
    assert movement_actions
    assert all("中等强度" not in action["title"] for action in movement_actions)
    assert any("暂停" in action["title"] or "休息" in action["title"] for action in movement_actions)
    assert body["movement_targets"]["weekly_moderate_minutes"] == 0
    assert body["state_summary"]["acute"]["should_rest_from_training"] is True
