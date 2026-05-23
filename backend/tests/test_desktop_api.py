from datetime import date


def test_desktop_bootstrap_requires_auth(client):
    resp = client.get("/api/v1/desktop/bootstrap")

    assert resp.status_code in {401, 403}


def test_desktop_bootstrap_returns_current_user_operating_context(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard
    from app.models.blood_pressure import BloodPressureRecord
    from app.models.daily_health import DietRecord, WaterIntake
    from app.models.memory_fact import MemoryFact
    from app.models.user import User
    from app.models.user_profile import UserProfile
    from app.models.weight import WeightRecord

    other = User(
        username="desktop_other",
        email="desktop_other@example.com",
        hashed_password="x",
        name="Other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    db.add(UserProfile(user_id=user.id, llm_model_id="claude-opus-4.7"))
    db.add(ActionCard(
        user_id=user.id,
        title="晚饭后散步",
        content="晚饭后走 20 分钟。",
        status="active",
        is_visible=True,
        priority=5,
    ))
    db.add(ActionCard(
        user_id=other.id,
        title="其他用户卡片",
        content="不应出现",
        status="active",
        is_visible=True,
        priority=99,
    ))
    db.add(MemoryFact(
        user_id=user.id,
        tier="semantic",
        subject="用户",
        predicate="prefers",
        object_value="晚上训练",
        confidence=0.8,
        tags=["desktop"],
    ))
    db.add(DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="breakfast",
        food_items="鸡蛋",
        calories=120,
    ))
    db.add(WaterIntake(
        user_id=user.id,
        record_date=date.today(),
        amount_ml=500,
        drink_type="water",
    ))
    db.add(DietRecord(
        user_id=user.id,
        record_date=date(2026, 5, 1),
        meal_type="dinner",
        food_items="牛肉面",
        calories=650,
    ))
    db.add(WaterIntake(
        user_id=user.id,
        record_date=date(2026, 5, 1),
        amount_ml=700,
        drink_type="water",
    ))
    db.add(WeightRecord(
        user_id=user.id,
        record_date=date(2026, 5, 2),
        weight=70.2,
        source="manual",
    ))
    db.add(BloodPressureRecord(
        user_id=user.id,
        record_date=date(2026, 5, 3),
        systolic=118,
        diastolic=76,
    ))
    db.commit()

    resp = client.get("/api/v1/desktop/bootstrap", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == user.id
    assert body["model_preference"]["llm_model_id"] == "claude-opus-4.7"
    assert body["daily_plan"]["plan_date"] == date.today().isoformat()
    assert "trajectory" in body
    assert [card["title"] for card in body["action_cards"]] == ["晚饭后散步"]
    assert body["recent_memory"][0]["object_value"] == "晚上训练"
    assert body["recent_records_summary"]["diet"]["today_count"] == 1
    assert body["recent_records_summary"]["diet"]["today_calories"] == 120
    assert body["recent_records_summary"]["diet"]["last_30_count"] == 2
    assert body["recent_records_summary"]["diet"]["last_30_calories"] == 770
    assert body["recent_records_summary"]["water"]["today_total_ml"] == 500
    assert body["recent_records_summary"]["water"]["last_30_total_ml"] == 1200
    assert body["recent_records_summary"]["latest_weight"]["value"] == 70.2
    assert body["recent_records_summary"]["latest_blood_pressure"]["value"] == "118/76"
    recent_types = [record["type"] for record in body["recent_records_summary"]["recent_records"]]
    assert "blood_pressure" in recent_types
    assert "weight" in recent_types
    assert body["active_jobs"] == []


def test_desktop_bootstrap_handles_empty_user_without_500(client, auth_user_and_headers):
    user, headers = auth_user_and_headers

    resp = client.get("/api/v1/desktop/bootstrap", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == user.id
    assert body["action_cards"] == []
    assert body["recent_memory"] == []
    assert body["active_jobs"] == []
