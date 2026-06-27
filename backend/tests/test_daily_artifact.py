"""Daily Artifact contract: one top action, concise evidence, anti-habituation events."""

from datetime import date


def test_daily_artifact_empty_state_degrades_cleanly(client, auth_user_and_headers, monkeypatch):
    from app.services import daily_artifact_service

    user, headers = auth_user_and_headers

    def fake_smart_today(db, user_id, followup_within_days=14, max_items=3):
        assert user_id == user.id
        return {
            "agenda_date": "2026-06-27",
            "mode": "smart",
            "source_count": 0,
            "smart": {"top_items": [], "ranking": "test"},
        }

    monkeypatch.setattr(daily_artifact_service.agenda_service, "smart_today", fake_smart_today)

    resp = client.get("/api/v1/daily-artifact/me", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["artifact_date"] == "2026-06-27"
    assert body["empty_state"] is True
    assert body["top_action"] is None
    assert body["evidence"] == []
    assert body["state"]["label"] == "暂无今日重点"
    assert body["safety_boundary"]


def test_daily_artifact_projects_single_top_action_and_three_evidence_items(
    client, auth_user_and_headers, monkeypatch
):
    from app.services import daily_artifact_service

    _, headers = auth_user_and_headers

    monkeypatch.setattr(
        daily_artifact_service.agenda_service,
        "smart_today",
        lambda db, user_id, followup_within_days=14, max_items=3: {
            "agenda_date": "2026-06-27",
            "mode": "smart",
            "source_count": 2,
            "smart": {
                "ranking": "trajectory_priority_status_source_v1",
                "top_items": [
                    {
                        "id": "smart_daily_plan_action_movement.walk_after_meal",
                        "type": "movement",
                        "title": "晚餐后步行 15 分钟",
                        "status": "pending",
                        "priority_tier": "P1",
                        "why_now": "餐后活动有助于今天的代谢管理。",
                        "do_now": "执行: 晚餐后步行 15 分钟",
                        "claim_boundary": "这是健康管理行动建议, 不替代医生诊断。",
                        "confidence": "high",
                        "source": {"object_type": "daily_plan_action", "object_id": "movement.walk_after_meal"},
                        "verify_by": {
                            "metrics": ["post_meal_walk_completed", "weight", "waist_cm", "hrv"],
                            "window_days": 7,
                            "trajectory": {
                                "domain": "metabolic_health",
                                "state_variable": "waist_cm",
                                "verification_signal": "waist_cm",
                            },
                        },
                        "trajectory_context": {
                            "domain": "metabolic_health",
                            "level": "attention",
                            "state_variable": "waist_cm",
                            "why": "腰围和血压提示代谢轨迹需要关注。",
                            "confidence": "high",
                        },
                    },
                    {
                        "id": "smart_health_protocol_99",
                        "title": "喝水",
                        "why_now": "低摩擦补水。",
                    },
                ],
            },
        },
    )

    resp = client.get("/api/v1/daily-artifact/me", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty_state"] is False
    assert body["top_action"]["id"] == "smart_daily_plan_action_movement.walk_after_meal"
    assert body["top_action"]["title"] == "晚餐后步行 15 分钟"
    assert body["top_action"]["why_now"].startswith("餐后活动")
    assert body["top_action"]["actions"]["complete"]["method"] == "POST"
    assert body["top_action"]["actions"]["skip"]["requires_reason"] is True
    assert len(body["evidence"]) == 3
    assert body["evidence"][0]["kind"] == "why_now"
    assert body["evidence"][1]["kind"] == "trajectory"
    assert body["evidence"][2]["kind"] == "verification"
    assert body["freshness"]["status"] in {"fresh", "limited"}
    assert body["safety_boundary"] == "这是健康管理行动建议, 不替代医生诊断。"


def test_daily_artifact_records_skip_reason_and_week_index(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers

    missing_reason = client.post(
        "/api/v1/daily-artifact/me/events",
        headers=headers,
        json={
            "event_type": "skipped",
            "artifact_date": "2026-06-27",
            "top_action_id": "smart_daily_plan_action_x",
        },
    )
    assert missing_reason.status_code == 400

    resp = client.post(
        "/api/v1/daily-artifact/me/events",
        headers=headers,
        json={
            "event_type": "skipped",
            "artifact_date": "2026-06-27",
            "top_action_id": "smart_daily_plan_action_x",
            "skip_reason": "no_time",
            "delivered_context": {"surface": "today", "evidence_count": 3},
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["event_type"] == "skipped"
    assert body["skip_reason"] == "no_time"
    assert body["week_index"] == 1

    from app.models.daily_artifact import DailyArtifactEvent

    row = db.query(DailyArtifactEvent).filter(DailyArtifactEvent.id == body["id"]).one()
    assert row.artifact_date == date(2026, 6, 27)
    assert row.delivered_context["surface"] == "today"
