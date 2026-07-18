from app.services.inline_cards import attach_card_action_policy_metadata


def test_card_write_action_carries_registered_capability_and_receipt_contract():
    actions = attach_card_action_policy_metadata(
        "diet_draft",
        [
            {
                "id": "confirm-diet-draft",
                "label": "确认记录",
                "action": "diet_record.create",
                "endpoint": "/diet/records",
                "requires_manual_confirm": True,
                "payload": {"record": {"food_items": "牛肉面", "meal_type": "lunch"}},
            }
        ],
    )

    assert actions == [
        {
            "id": "confirm-diet-draft",
            "label": "确认记录",
            "action": "diet_record.create",
            "endpoint": "/diet/records",
            "requires_manual_confirm": True,
            "payload": {"record": {"food_items": "牛肉面", "meal_type": "lunch"}},
            "capability_id": "diet_draft.v1",
            "required_receipt": True,
            "autonomy_tier": "manual_confirm",
            "policy_reason": "manual_confirm_write",
        }
    ]


def test_card_read_action_carries_suggest_policy_without_receipt_requirement():
    actions = attach_card_action_policy_metadata(
        "metric_chart",
        [
            {
                "id": "open-weight-history",
                "label": "查看体重历史",
                "action": "route.open",
                "payload": {"route": "/indicator-history?type=weight"},
            }
        ],
    )

    assert actions[0]["capability_id"] == "metric_chart.v1"
    assert actions[0]["required_receipt"] is False
    assert actions[0]["autonomy_tier"] == "suggest"
    assert actions[0]["policy_reason"] == "registered_read_action"
