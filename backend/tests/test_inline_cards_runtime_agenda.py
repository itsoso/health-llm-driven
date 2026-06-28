"""Chat inline runtime-agenda card contract."""


def test_inline_cards_builds_runtime_agenda_card(monkeypatch):
    from app.services import inline_cards

    calls = {}

    def fake_runtime_range_view(db, user_id, days=7, max_items_per_day=3):
        calls["user_id"] = user_id
        calls["days"] = days
        calls["max_items_per_day"] = max_items_per_day
        action = {
            "id": "smart_daily_plan_action_walk",
            "type": "movement",
            "title": "晚餐后步行 15 分钟",
            "time_window": "evening",
            "priority_tier": "P1",
            "source": {"object_type": "daily_plan_action", "object_id": "walk"},
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
        return {
            "mode": "runtime",
            "generated_by": "rolling_health_runtime_v1",
            "horizon_days": 7,
            "start": "2026-06-28",
            "end": "2026-07-04",
            "next_action": action,
            "runtime_context": {"safety_boundary": "这是健康管理行动建议, 不替代医生诊断。"},
            "days": [
                {"date": "2026-06-28", "next_action": action, "time_windows": [{"label": "evening", "items": [action]}]},
                {"date": "2026-06-29", "next_action": None, "time_windows": [{"label": "morning", "items": []}]},
            ],
        }

    monkeypatch.setattr(inline_cards.agenda_service, "runtime_range_view", fake_runtime_range_view)

    cards = inline_cards.build_cards(db=None, user_id=3, query="接下来7天我应该怎么安排健康行动？")

    assert calls == {"user_id": 3, "days": 7, "max_items_per_day": 3}
    assert cards[0]["type"] == "runtime_agenda"
    assert cards[0]["data"]["generated_by"] == "rolling_health_runtime_v1"
    assert cards[0]["data"]["horizon_days"] == 7
    assert cards[0]["data"]["next_action"]["title"] == "晚餐后步行 15 分钟"
    assert cards[0]["data"]["next_action"]["replan_reason"] == "today_smart_rank"
    assert cards[0]["data"]["next_action"]["verification_metrics"] == [
        "post_meal_walk_completed",
        "waist_cm",
        "hrv",
    ]
    assert cards[0]["actions"] == [
        {
            "id": "open-runtime-agenda",
            "label": "查看7天计划",
            "action": "route.open",
            "payload": {"route": "/agenda"},
            "style": "primary",
        }
    ]


def test_inline_cards_runtime_agenda_does_not_trigger_for_record_intent(monkeypatch):
    from app.services import inline_cards

    monkeypatch.setattr(
        inline_cards.agenda_service,
        "runtime_range_view",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call runtime")),
    )

    cards = inline_cards.build_cards(db=None, user_id=3, query="记录我刚喝了200ml水")

    assert all(card["type"] != "runtime_agenda" for card in cards)
