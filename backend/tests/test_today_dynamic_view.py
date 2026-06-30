"""Today DynamicView contract composed by Aheng."""


def test_today_dynamic_view_returns_composable_cards(client, auth_user_and_headers, monkeypatch):
    from app.services import today_dynamic_view_service

    user, headers = auth_user_and_headers
    runtime_action = {
        "id": "smart_daily_plan_action_walk",
        "type": "movement",
        "title": "晚餐后步行 15 分钟",
        "time_window": "evening",
        "priority_tier": "P1",
        "runtime_context": {
            "current_state_summary": "晚餐后是今天最短的代谢干预窗口。",
            "replan_reason": "today_smart_rank",
            "safety_boundary": "这是健康管理行动建议, 不替代医生诊断。",
            "verification_window": {
                "metrics": ["post_meal_walk_completed", "waist_cm", "hrv"],
                "window_days": 7,
            },
        },
    }

    def fake_artifact(db, user_id, followup_within_days=7):
        assert user_id == user.id
        assert followup_within_days == 7
        return {
            "artifact_date": "2026-06-29",
            "generated_by": "daily_artifact_runtime_v1",
            "source": {"kind": "agenda.runtime_range"},
            "empty_state": False,
            "state": {"label": "今日最重要行动", "tone": "focused", "summary": "先完成餐后步行。"},
            "top_action": {
                "id": "smart_daily_plan_action_walk",
                "title": "晚餐后步行 15 分钟",
                "actions": {"complete": {"enabled": True}, "skip": {"requires_reason": True}},
            },
            "evidence": [],
            "confidence": "medium",
            "freshness": {"status": "fresh", "sources": ["agenda.runtime_range"]},
            "safety_boundary": "这是健康管理行动建议, 不替代医生诊断。",
        }

    def fake_runtime(db, user_id, days=7, max_items_per_day=3):
        assert user_id == user.id
        assert days == 7
        assert max_items_per_day == 3
        return {
            "mode": "runtime",
            "generated_by": "rolling_health_runtime_v1",
            "horizon_days": 7,
            "start": "2026-06-29",
            "end": "2026-07-05",
            "next_action": runtime_action,
            "runtime_context": {"safety_boundary": "这是健康管理行动建议, 不替代医生诊断。"},
            "days": [
                {
                    "date": "2026-06-29",
                    "next_action": runtime_action,
                    "time_windows": [{"label": "evening", "items": [runtime_action]}],
                },
            ],
        }

    monkeypatch.setattr(today_dynamic_view_service.daily_artifact_service, "build_daily_artifact", fake_artifact)
    monkeypatch.setattr(today_dynamic_view_service.agenda_service, "runtime_range_view", fake_runtime)

    resp = client.post(
        "/api/v1/dynamic-views/today",
        headers=headers,
        json={
            "surface": "mobile.today",
            "trigger": "open",
            "client_context": {"timezone": "Asia/Shanghai", "client_capabilities": ["daily_artifact"]},
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["surface"] == "mobile.today"
    assert body["trigger"] == "open"
    assert body["generated_by"] == "aheng_today_view_v1"
    assert body["view_id"].startswith("today:2026-06-29:")
    assert body["context_hash"]
    assert body["safety_boundary"] == "这是健康管理行动建议, 不替代医生诊断。"
    assert {section["slot"] for section in body["sections"]} == {"hero", "runtime"}

    hero = next(section for section in body["sections"] if section["slot"] == "hero")
    assert hero["cards"][0]["type"] == "daily_artifact"
    assert hero["cards"][0]["data"]["top_action"]["title"] == "晚餐后步行 15 分钟"

    runtime = next(section for section in body["sections"] if section["slot"] == "runtime")
    card = runtime["cards"][0]
    assert card["type"] == "runtime_agenda"
    assert card["data"]["generated_by"] == "rolling_health_runtime_v1"
    assert card["data"]["next_action"]["replan_reason"] == "today_smart_rank"
    assert card["actions"] == [
        {
            "id": "open-runtime-agenda",
            "label": "查看7天计划",
            "action": "route.open",
            "payload": {"route": "/agenda"},
            "style": "primary",
        }
    ]


def test_today_dynamic_view_rejects_unknown_surface(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/dynamic-views/today",
        headers=headers,
        json={"surface": "mobile.dashboard", "trigger": "open", "client_context": {}},
    )

    assert resp.status_code == 422
