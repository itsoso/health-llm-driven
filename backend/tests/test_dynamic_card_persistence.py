from app.services.dynamic_card_persistence import cards_for_persistence


def test_diet_draft_persistence_removes_ephemeral_signed_photo_url():
    cards = [{
        "type": "diet_draft",
        "data": {
            "photo_asset_id": "photo-1",
            "photo_url": "/api/v1/upload/files/diet/7/lunch.jpg?expires=1&signature=secret",
            "food_items": "鸡胸肉和杂粮饭",
        },
        "actions": [],
    }]

    persisted = cards_for_persistence(cards)

    assert persisted[0]["data"] == {
        "photo_asset_id": "photo-1",
        "food_items": "鸡胸肉和杂粮饭",
    }
    assert "photo_url" in cards[0]["data"]


def test_non_diet_cards_keep_their_existing_persistence_contract():
    cards = [{
        "type": "system_knowledge_evidence",
        "data": {"title": "证据", "url": "https://example.test/evidence"},
        "actions": [],
    }]

    assert cards_for_persistence(cards) == cards
