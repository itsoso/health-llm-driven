from datetime import datetime, timezone


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

    expires_at = datetime.fromisoformat(data["expires_at"])
    created_at = datetime.fromisoformat(data["created_at"])
    if expires_at.tzinfo and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    assert expires_at > created_at


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
