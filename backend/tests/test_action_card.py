from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError


def test_create_action_card_preserves_structured_intervention_fields(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/action-cards",
        headers=headers,
        json={
            "title": "提前晚餐实验",
            "content": "未来 7 天把晚餐提前到 19:00 前，观察睡眠评分变化。",
            "card_type": "plan",
            "source_type": "chat",
            "source_id": "msg-1",
            "priority": 2,
            "metric_key": "sleep_score",
            "baseline_value": "76",
            "target_value": "82",
            "verification_days": 7,
            "checklist": [
                {"item": "19:00 前完成晚餐", "done": False},
                {"item": "记录睡眠评分", "done": False},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metric_key"] == "sleep_score"
    assert data["baseline_value"] == "76"
    assert data["target_value"] == "82"
    assert data["verification_days"] == 7
    assert data["checklist"] == [
        {"item": "19:00 前完成晚餐", "done": False},
        {"item": "记录睡眠评分", "done": False},
    ]

    assert data["expires_at"] is None
    check_back_at = datetime.fromisoformat(data["check_back_date"])
    created_at = datetime.fromisoformat(data["created_at"])
    if check_back_at.tzinfo and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    assert check_back_at > created_at


def test_create_action_card_rejects_invalid_metric_key(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/action-cards",
        headers=headers,
        json={
            "title": "无效指标",
            "content": "不应该接受未知指标。",
            "metric_key": "unknown_metric",
        },
    )

    assert response.status_code == 422


def test_create_action_card_can_atomically_accept_explicit_today_action(
    client, auth_user_and_headers, db
):
    user, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/action-cards",
        headers=headers,
        json={
            "title": "今晚暂停高强度训练",
            "content": "今天只做轻活动，明早回看恢复状态。",
            "card_type": "plan",
            "source_type": "chat",
            "source_id": "msg-today-1",
            "metric_key": "hrv",
            "verification_days": 1,
            "accepted": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_decision"] == "accepted"
    assert data["decided_at"] is not None
    assert data["expires_at"] is None
    assert data["check_back_date"] is not None

    from app.services.daily_operating_plan import _active_interventions

    active = _active_interventions(db, user.id)
    assert any(
        item["source_card_id"] == data["id"]
        and item["title"] == "今晚暂停高强度训练"
        for item in active
    )

    # 复盘窗口不是过期时间。到了次日复盘点，行动仍应保留，直到用户完成或归档。
    future = datetime.fromisoformat(data["check_back_date"]) + timedelta(minutes=1)
    active_at_review = _active_interventions(db, user.id, now=future)
    assert any(item["source_card_id"] == data["id"] for item in active_at_review)


def test_create_accepted_chat_action_is_idempotent_per_source_and_title(
    client, auth_user_and_headers, db
):
    user, headers = auth_user_and_headers
    payload = {
        "title": "今晚暂停高强度训练",
        "content": "今天只做轻活动。",
        "card_type": "plan",
        "source_type": "chat",
        "source_id": "msg-today-idempotent",
        "verification_days": 1,
        "accepted": True,
    }

    first = client.post("/api/v1/action-cards", headers=headers, json=payload)
    second = client.post("/api/v1/action-cards", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    from app.models.action_card import ActionCard

    assert db.query(ActionCard).filter(
        ActionCard.user_id == user.id,
        ActionCard.source_type == "chat",
        ActionCard.source_id == "msg-today-idempotent",
        ActionCard.title == payload["title"],
    ).count() == 1


def test_accepted_action_card_database_key_blocks_concurrent_duplicates(
    client, auth_user_and_headers, db
):
    user, headers = auth_user_and_headers
    payload = {
        "title": "今晚散步 10 分钟",
        "content": "晚餐后轻松散步，明早回看恢复状态。",
        "card_type": "plan",
        "source_type": "chat",
        "source_id": "msg-concurrent-idempotent",
        "accepted": True,
    }
    response = client.post("/api/v1/action-cards", headers=headers, json=payload)
    assert response.status_code == 200

    from app.models.action_card import ActionCard

    created = db.query(ActionCard).filter(ActionCard.id == response.json()["id"]).one()
    duplicate = ActionCard(
        user_id=user.id,
        title=payload["title"],
        content=payload["content"],
        source_type=payload["source_type"],
        source_id=payload["source_id"],
        user_decision="accepted",
        accepted_create_key=created.accepted_create_key,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize(
    ("title", "content"),
    [
        ("停用二甲双胍", "从今天开始停用二甲双胍。"),
        ("调整降糖药", "把二甲双胍换成格列美脲。"),
        ("调整降糖药", "二甲双胍改用格列美脲。"),
        ("增加二甲双胍", "二甲双胍从每天一片改为两片。"),
        ("减少二甲双胍", "二甲双胍减半。"),
        ("停用降压药", "把降压药停了。"),
        ("停用降压药", "降压药今天先停。"),
        ("停用二甲双胍", "二甲双胍从明天开始停了。"),
        ("停用二甲双胍", "明天不吃二甲双胍。"),
        ("减少二甲双胍", "二甲双胍明天减一片。"),
        ("增加二甲双胍", "二甲双胍明天加一片。"),
        ("用药安全", "不要自行停药；现在把二甲双胍减半。"),
    ],
)
def test_create_accepted_action_card_blocks_unreviewed_medication_change(
    client, auth_user_and_headers, title, content
):
    _, headers = auth_user_and_headers
    response = client.post(
        "/api/v1/action-cards",
        headers=headers,
        json={
            "title": title,
            "content": content,
            "card_type": "plan",
            "source_type": "chat",
            "source_id": "msg-unsafe-medication-change",
            "accepted": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "advice_guard_blocked"


def test_create_action_card_keeps_default_unaccepted(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/action-cards",
        headers=headers,
        json={
            "title": "稍后再决定",
            "content": "这条建议仍需用户确认。",
            "accepted": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_decision"] is None
    assert data["decided_at"] is None


def test_review_action_card_persists_latest_assessment(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    create_response = client.post(
        "/api/v1/action-cards",
        headers=headers,
        json={
            "title": "提前晚餐实验",
            "content": "未来 7 天把晚餐提前到 19:00 前。",
            "card_type": "plan",
            "metric_key": "sleep_score",
            "baseline_value": "76",
            "target_value": "82",
            "verification_days": 7,
        },
    )
    card_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/action-cards/{card_id}/review",
        headers=headers,
        json={
            "status": "completed",
            "outcome_status": "met",
            "actual_value": "84",
            "latest_assessment": {
                "score": 8,
                "summary": "睡眠评分达到目标",
                "evidence": ["Garmin sleep_score"],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["latest_assessment"]["score"] == 8
    assert data["latest_assessment"]["outcome_status"] == "met"
    assert data["latest_assessment"]["actual_value"] == "84"
    assert data["completed_at"] is not None


def test_get_active_action_cards_archives_expired_cards(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard

    expired = ActionCard(
        user_id=user.id,
        title="过期建议",
        content="这个建议已经过期。",
        status="active",
        is_visible=True,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    active = ActionCard(
        user_id=user.id,
        title="仍然有效建议",
        content="这个建议仍然有效。",
        status="active",
        is_visible=True,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add_all([expired, active])
    db.commit()
    db.refresh(expired)
    db.refresh(active)

    response = client.get("/api/v1/action-cards/me?status=active", headers=headers)

    assert response.status_code == 200
    ids = [card["id"] for card in response.json()]
    assert active.id in ids
    assert expired.id not in ids

    db.refresh(expired)
    assert expired.status == "archived"
    assert expired.is_visible is False


def test_action_card_api_hides_legacy_clinician_gated_score(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard

    card = ActionCard(
        user_id=user.id,
        title="降低 LDL",
        content="保留测量供临床复盘。",
        status="active",
        is_visible=True,
        metric_key="ldl",
        accuracy_score=95,
        outcome="improved",
        effect_size=0.8,
    )
    db.add(card)
    db.commit()

    response = client.get("/api/v1/action-cards/me?status=active", headers=headers)

    assert response.status_code == 200
    payload = next(item for item in response.json() if item["id"] == card.id)
    assert payload["accuracy_score"] is None
    assert payload["score_status"] == "clinician_review"
    assert payload["outcome"] == "inconclusive"
    assert payload["effect_size"] is None


def test_get_active_action_cards_archives_legacy_weekly_cards_without_expires(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard

    legacy = ActionCard(
        user_id=user.id,
        title="旧本周建议",
        content="历史数据没有 expires_at, 也不应永久留在首页。",
        status="active",
        is_visible=True,
        source_type="weekly_advisor",
        user_decision="accepted",
        created_at=datetime.now(timezone.utc) - timedelta(days=21),
    )
    db.add(legacy)
    db.commit()
    db.refresh(legacy)

    response = client.get("/api/v1/action-cards/me?status=active", headers=headers)

    assert response.status_code == 200
    ids = [card["id"] for card in response.json()]
    assert legacy.id not in ids

    db.refresh(legacy)
    assert legacy.status == "archived"
    assert legacy.is_visible is False
