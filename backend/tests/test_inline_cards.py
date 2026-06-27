from app.services import today_timeline_service
from app.services.inline_cards import build_cards


def test_build_cards_emits_agenda_action_with_allowlisted_actions(db, monkeypatch):
    def fake_today_spine(_db, user_id):
        assert user_id == 3
        return {
            "now": "hydration-1",
            "items": [
                {
                    "id": "hydration-1",
                    "title": "喝 200ml 温水",
                    "subtitle": "起床后补水,再开始运动",
                    "scheduled_for": "08:00",
                    "can_complete": True,
                    "complete_ref": {"object_type": "health_protocol", "object_id": 12},
                    "deep_link": "/agenda",
                }
            ],
        }

    monkeypatch.setattr(today_timeline_service, "build_today_spine", fake_today_spine)

    cards = build_cards(db, 3, "今天我该做什么")

    assert cards[0]["type"] == "agenda_action"
    assert cards[0]["data"] == {
        "id": "hydration-1",
        "title": "喝 200ml 温水",
        "subtitle": "起床后补水",
        "scheduled_for": "08:00",
        "source": {"object_type": "health_protocol", "object_id": 12},
        "deep_link": "/agenda",
    }
    assert cards[0]["actions"] == [
        {
            "action": "complete_agenda",
            "endpoint": "/agenda/complete",
            "label": "完成",
            "payload": {"source": {"object_type": "health_protocol", "object_id": 12}},
            "style": "primary",
        },
        {
            "action": "skip_agenda",
            "endpoint": "/agenda/complete",
            "label": "太累,跳过",
            "payload": {
                "source": {"object_type": "health_protocol", "object_id": 12},
                "skip_reason": "too_tired",
            },
            "style": "secondary",
        },
    ]
