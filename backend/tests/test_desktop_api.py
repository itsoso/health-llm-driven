from datetime import date


def test_desktop_bootstrap_requires_auth(client):
    resp = client.get("/api/v1/desktop/bootstrap")

    assert resp.status_code in {401, 403}


def test_desktop_bootstrap_returns_current_user_operating_context(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard
    from app.models.daily_health import DietRecord, WaterIntake
    from app.models.memory_fact import MemoryFact
    from app.models.user import User
    from app.models.user_profile import UserProfile

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
    assert body["recent_records_summary"]["water"]["today_total_ml"] == 500
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
