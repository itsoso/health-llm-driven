from datetime import date, datetime, timedelta, timezone

from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord
from app.services.dynamic_card_persistence import (
    cards_for_persistence,
    message_metas_for_delivery,
)
from tests.conftest import create_authenticated_user


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


def test_diet_draft_persistence_removes_all_ephemeral_photo_urls():
    cards = [{
        "type": "diet_draft",
        "data": {
            "card_id": "diet-record:42",
            "photo_asset_id": "photo-1",
            "photo_asset_ids": ["photo-1", "photo-2"],
            "photo_url": "/api/v1/upload/files/diet/7/one.jpg?signature=one",
            "photo_urls": [
                "/api/v1/upload/files/diet/7/one.jpg?signature=one",
                "/api/v1/upload/files/diet/7/two.jpg?signature=two",
            ],
        },
        "actions": [],
    }]

    persisted = cards_for_persistence(cards)

    assert persisted[0]["data"] == {
        "card_id": "diet-record:42",
        "photo_asset_id": "photo-1",
        "photo_asset_ids": ["photo-1", "photo-2"],
    }


def test_draft_card_recovers_current_record_parent_after_confirmation(db):
    user, _ = create_authenticated_user(db)
    draft = DietPhotoDraft(
        token="stable-card-draft-token",
        user_id=user.id,
        source_message_id=991,
        image_url=f"/api/v1/upload/files/diet/{user.id}/meal.jpg",
        image_type="jpeg",
        recognition_result={"food_items": "鸡胸肉", "calories": 220},
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    asset = DietPhotoAsset(
        id="stable-card-asset",
        user_id=user.id,
        photo_draft_token=draft.token,
        storage_key=f"/api/v1/upload/files/diet/{user.id}/meal.jpg",
        content_sha256="a" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=991,
        ordinal=0,
        classification="food",
        recognition_confidence=0.93,
        intent_decision="confirm",
        recognition_snapshot={},
        lifecycle="pending",
    )
    db.add_all([draft, asset])
    db.commit()
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="鸡胸肉",
        food_items="鸡胸肉",
        source="chat_photo",
        client_action_id=f"diet-photo:{draft.token}",
        calories=220,
    )
    db.add(record)
    db.flush()
    asset.diet_record_id = record.id
    asset.photo_draft_token = None
    asset.lifecycle = "attached"
    db.delete(draft)
    db.commit()
    meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": "diet-capture:meal-photo:991",
                "capture_session_id": "meal-photo:991",
                "recorded": False,
                "photo_draft_token": "stable-card-draft-token",
                "photo_asset_id": asset.id,
                "photo_asset_ids": [asset.id],
            },
            "actions": [{"action": "diet_record.create"}],
        }],
    }

    delivered = message_metas_for_delivery(db, [meta], user.id)

    card = delivered[0]["cards"][0]
    assert card["data"]["card_id"] == "diet-capture:meal-photo:991"
    assert card["data"]["recorded"] is True
    assert card["data"]["record_id"] == record.id
    assert "photo_draft_token" not in card["data"]
    assert card["data"]["media_stage"] == "attached"
    assert card["data"]["photo_asset_ids"] == [asset.id]
    assert card["data"]["photo_url"]
    assert card["actions"] == []


def test_failed_diet_photo_signature_counts_asset_as_unavailable(
    db, monkeypatch
):
    user, _ = create_authenticated_user(db)
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="鸡胸肉",
        food_items="鸡胸肉",
        source="chat_photo",
    )
    db.add(record)
    db.flush()
    asset = DietPhotoAsset(
        id="unsignable-card-asset",
        user_id=user.id,
        diet_record_id=record.id,
        storage_key=f"/api/v1/upload/files/diet/{user.id}/meal.jpg",
        content_sha256="b" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=992,
        ordinal=0,
        classification="food",
        recognition_confidence=0.93,
        intent_decision="auto_record",
        recognition_snapshot={},
        lifecycle="attached",
    )
    db.add(asset)
    db.commit()
    monkeypatch.setattr(
        "app.utils.diet_image_url.diet_response_image_url",
        lambda *_args, **_kwargs: None,
    )
    meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": "diet-capture:meal-photo:992",
                "capture_session_id": "meal-photo:992",
                "recorded": True,
                "record_id": record.id,
                "photo_asset_ids": [asset.id],
            },
            "actions": [],
        }],
    }

    delivered = message_metas_for_delivery(db, [meta], user.id)

    data = delivered[0]["cards"][0]["data"]
    assert data["photo_asset_ids"] == []
    assert data["photo_unavailable_count"] == 1
    assert data["media_stage"] == "unavailable"
    assert "photo_url" not in data
    assert "photo_urls" not in data


def test_capture_session_restores_assets_added_after_card_was_persisted(db):
    user, _ = create_authenticated_user(db)
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="鸡胸肉和西兰花",
        food_items="鸡胸肉和西兰花",
        source="chat_photo",
    )
    db.add(record)
    db.flush()
    assets = [
        DietPhotoAsset(
            id=f"expanded-card-asset-{ordinal}",
            user_id=user.id,
            diet_record_id=record.id,
            storage_key=(
                f"/api/v1/upload/files/diet/{user.id}/expanded-{ordinal}.jpg"
            ),
            content_sha256=str(ordinal + 5) * 64,
            media_type="image/jpeg",
            origin="chat",
            origin_message_id=994,
            ordinal=ordinal,
            classification="food",
            recognition_confidence=0.93,
            intent_decision="auto_record",
            recognition_snapshot={},
            lifecycle="attached",
        )
        for ordinal in range(2)
    ]
    db.add_all(assets)
    db.commit()
    meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": "diet-capture:meal-photo:994",
                "capture_session_id": "meal-photo:994",
                "recorded": True,
                "record_id": record.id,
                # This is the durable card written before the second image was
                # attached to the same capture session.
                "photo_asset_ids": [assets[0].id],
            },
            "actions": [],
        }],
    }

    delivered = message_metas_for_delivery(db, [meta], user.id)

    data = delivered[0]["cards"][0]["data"]
    assert data["photo_asset_ids"] == [asset.id for asset in assets]
    assert len(data["photo_urls"]) == 2
    assert data["media_stage"] == "attached"


def test_capture_session_never_recovers_another_owners_asset(db):
    owner, _ = create_authenticated_user(db)
    viewer, _ = create_authenticated_user(db)
    record = DietRecord(
        user_id=owner.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="私有餐食",
        food_items="私有餐食",
        source="chat_photo",
    )
    db.add(record)
    db.flush()
    asset = DietPhotoAsset(
        id="other-owner-card-asset",
        user_id=owner.id,
        diet_record_id=record.id,
        storage_key=f"/api/v1/upload/files/diet/{owner.id}/private.jpg",
        content_sha256="c" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=993,
        ordinal=0,
        classification="food",
        recognition_confidence=0.93,
        intent_decision="auto_record",
        recognition_snapshot={},
        lifecycle="attached",
    )
    db.add(asset)
    db.commit()
    meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": "diet-capture:meal-photo:993",
                "capture_session_id": "meal-photo:993",
                "photo_asset_ids": [asset.id],
            },
            "actions": [],
        }],
    }

    delivered = message_metas_for_delivery(db, [meta], viewer.id)

    data = delivered[0]["cards"][0]["data"]
    assert data["photo_asset_ids"] == []
    assert data["media_stage"] == "unavailable"
