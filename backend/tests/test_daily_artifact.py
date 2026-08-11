"""Daily Artifact contract: one top action, concise evidence, anti-habituation events."""

from datetime import date


def test_daily_artifact_completion_contract_uses_the_owned_write_endpoint():
    from app.services.daily_artifact_service import _top_action_view

    daily_plan = _top_action_view({
        "id": "smart_daily_plan_action_movement.walk_after_meal",
        "title": "晚餐后步行 15 分钟",
        "status": "pending",
        "can_complete": True,
        "source": {
            "object_type": "daily_plan_action",
            "object_id": "movement.walk_after_meal",
        },
    })
    protocol = _top_action_view({
        "id": "smart_health_protocol_7",
        "title": "饮水",
        "status": "pending",
        "can_complete": True,
        "source": {"object_type": "health_protocol", "object_id": 7},
    })

    assert daily_plan["actions"]["complete"]["endpoint"] == (
        "/api/v1/daily-plan/actions/movement.walk_after_meal/events"
    )
    assert daily_plan["actions"]["complete"]["payload"] == {"event_type": "completed"}
    assert protocol["actions"]["complete"]["endpoint"] == "/api/v1/agenda/complete"


def test_daily_artifact_empty_state_degrades_cleanly(client, auth_user_and_headers, monkeypatch):
    from app.services import daily_artifact_service

    user, headers = auth_user_and_headers

    def fake_runtime_range_view(db, user_id, days=7, max_items_per_day=3):
        assert user_id == user.id
        assert days == 7
        assert max_items_per_day == 3
        return {
            "start": "2026-06-27",
            "end": "2026-07-03",
            "mode": "runtime",
            "generated_by": "rolling_health_runtime_v1",
            "horizon_days": 7,
            "next_action": None,
            "runtime_context": {
                "safety_boundary": "这是运行时健康管理行动建议, 不替代医生诊断。",
            },
            "days": [
                {
                    "date": "2026-06-27",
                    "time_windows": [],
                    "next_action": None,
                }
            ],
        }

    monkeypatch.setattr(daily_artifact_service.agenda_service, "runtime_range_view", fake_runtime_range_view)

    resp = client.get("/api/v1/daily-artifact/me", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["artifact_date"] == "2026-06-27"
    assert body["empty_state"] is True
    assert body["generated_by"] == "daily_artifact_runtime_v1"
    assert body["source"]["kind"] == "agenda.runtime_range"
    assert body["source"]["runtime_generated_by"] == "rolling_health_runtime_v1"
    assert body["source"]["horizon_days"] == 7
    assert body["top_action"] is None
    assert body["evidence"] == []
    assert body["state"]["label"] == "暂无今日重点"
    assert body["safety_boundary"]


def test_daily_artifact_projects_single_top_action_and_three_evidence_items(
    client, auth_user_and_headers, monkeypatch
):
    from app.services import daily_artifact_service

    user, headers = auth_user_and_headers

    runtime_action = {
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
        "runtime_context": {
            "current_state_summary": "晚餐后是今天最短的代谢干预窗口。",
            "replan_reason": "today_smart_rank",
            "verification_window": {
                "metrics": ["post_meal_walk_completed", "weight", "waist_cm", "hrv"],
                "window_days": 7,
            },
            "safety_boundary": "这是运行时健康管理行动建议, 不替代医生诊断。",
        },
    }

    def fake_runtime_range_view(db, user_id, days=7, max_items_per_day=3):
        assert user_id == user.id
        assert days == 7
        assert max_items_per_day == 3
        return {
            "start": "2026-06-27",
            "end": "2026-07-03",
            "mode": "runtime",
            "generated_by": "rolling_health_runtime_v1",
            "horizon_days": 7,
            "next_action": runtime_action,
            "runtime_context": {
                "safety_boundary": "这是运行时健康管理行动建议, 不替代医生诊断。",
            },
            "days": [
                {
                    "date": "2026-06-27",
                    "time_windows": [{"label": "evening", "items": [runtime_action]}],
                    "next_action": runtime_action,
                }
            ],
        }

    monkeypatch.setattr(daily_artifact_service.agenda_service, "runtime_range_view", fake_runtime_range_view)

    resp = client.get("/api/v1/daily-artifact/me", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["empty_state"] is False
    assert body["generated_by"] == "daily_artifact_runtime_v1"
    assert body["source"]["kind"] == "agenda.runtime_range"
    assert body["source"]["runtime_generated_by"] == "rolling_health_runtime_v1"
    assert body["source"]["horizon_days"] == 7
    assert body["top_action"]["id"] == "smart_daily_plan_action_movement.walk_after_meal"
    assert body["top_action"]["title"] == "晚餐后步行 15 分钟"
    assert body["top_action"]["why_now"].startswith("餐后活动")
    assert body["top_action"]["trajectory_context"]["state_variable"] == "waist_cm"
    assert body["top_action"]["target_state_variable"] == "waist_cm"
    assert body["top_action"]["verification_signal"] == "waist_cm"
    assert body["top_action"]["claim_boundary"] == "这是健康管理行动建议, 不替代医生诊断。"
    assert body["top_action"]["runtime_context"]["replan_reason"] == "today_smart_rank"
    assert body["top_action"]["actions"]["complete"]["method"] == "POST"
    assert body["top_action"]["actions"]["skip"]["requires_reason"] is True
    assert len(body["evidence"]) == 3
    assert body["evidence"][0]["kind"] == "why_now"
    assert body["evidence"][1]["kind"] == "trajectory"
    assert body["evidence"][2]["kind"] == "verification"
    assert body["freshness"]["status"] in {"fresh", "limited"}
    assert body["safety_boundary"] == "这是健康管理行动建议, 不替代医生诊断。"


def test_daily_artifact_detail_query_recovers_matching_action(client, auth_user_and_headers, monkeypatch):
    from app.services import daily_artifact_service

    user, headers = auth_user_and_headers
    runtime_action = {
        "id": "today-recovery",
        "type": "movement",
        "title": "今天先轻活动",
        "status": "pending",
        "why_now": "恢复日先降低强度。",
        "source": {"object_type": "daily_plan_action", "object_id": "movement.recovery"},
    }

    def fake_runtime_range_view(db, user_id, days=7, max_items_per_day=3):
        assert user_id == user.id
        assert days == 7
        assert max_items_per_day == 3
        return {
            "start": "2026-06-29",
            "end": "2026-07-05",
            "mode": "runtime",
            "generated_by": "rolling_health_runtime_v1",
            "horizon_days": 7,
            "next_action": runtime_action,
            "runtime_context": {
                "safety_boundary": "这是运行时健康管理行动建议, 不替代医生诊断。",
            },
            "days": [
                {
                    "date": "2026-06-29",
                    "time_windows": [{"label": "morning", "items": [runtime_action]}],
                    "next_action": runtime_action,
                }
            ],
        }

    monkeypatch.setattr(daily_artifact_service.agenda_service, "runtime_range_view", fake_runtime_range_view)

    resp = client.get(
        "/api/v1/daily-artifact/me",
        headers=headers,
        params={"artifact_date": "2026-06-29", "top_action_id": "today-recovery"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["artifact_date"] == "2026-06-29"
    assert body["top_action"]["id"] == "today-recovery"
    assert body["top_action"]["title"] == "今天先轻活动"


def test_daily_artifact_detail_query_rejects_mismatched_action(client, auth_user_and_headers, monkeypatch):
    from app.services import daily_artifact_service

    user, headers = auth_user_and_headers
    runtime_action = {
        "id": "today-recovery",
        "type": "movement",
        "title": "今天先轻活动",
        "status": "pending",
        "why_now": "恢复日先降低强度。",
        "source": {"object_type": "daily_plan_action", "object_id": "movement.recovery"},
    }

    def fake_runtime_range_view(db, user_id, days=7, max_items_per_day=3):
        assert user_id == user.id
        return {
            "start": "2026-06-29",
            "end": "2026-07-05",
            "mode": "runtime",
            "generated_by": "rolling_health_runtime_v1",
            "horizon_days": days,
            "next_action": runtime_action,
            "runtime_context": {
                "safety_boundary": "这是运行时健康管理行动建议, 不替代医生诊断。",
            },
            "days": [
                {
                    "date": "2026-06-29",
                    "time_windows": [{"label": "morning", "items": [runtime_action]}],
                    "next_action": runtime_action,
                }
            ],
        }

    monkeypatch.setattr(daily_artifact_service.agenda_service, "runtime_range_view", fake_runtime_range_view)

    action_resp = client.get(
        "/api/v1/daily-artifact/me",
        headers=headers,
        params={"artifact_date": "2026-06-29", "top_action_id": "other-action"},
    )
    date_resp = client.get(
        "/api/v1/daily-artifact/me",
        headers=headers,
        params={"artifact_date": "2026-06-28", "top_action_id": "today-recovery"},
    )

    assert action_resp.status_code == 404
    assert action_resp.json()["detail"] == "daily_artifact_action_not_found"
    assert date_resp.status_code == 404
    assert date_resp.json()["detail"] == "daily_artifact_date_not_found"


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
