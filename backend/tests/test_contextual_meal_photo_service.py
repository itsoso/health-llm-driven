"""Persistence contracts for contextual chat meal photos."""
from datetime import datetime, timezone

import pytest

from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord
from app.models.user import User
from app.services.contextual_meal_photo_policy import (
    MealPhotoCandidate,
    MealPhotoSemanticIntent,
    decide_contextual_meal_photo,
)
from app.services.contextual_meal_photo_service import (
    ContextualMealPhotoCapture,
    ContextualMealPhotoService,
    ContextualMealPhotoServiceError,
)
from app.services import chat_utils


VALID_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z/QAAAABJRU5ErkJggg=="


@pytest.fixture
def test_user(db):
    user = User(
        username="contextual_meal_photo_user",
        email="contextual-meal-photo@example.com",
        hashed_password="hashed_password",
        name="餐食照片测试用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _decision(*, at: datetime, timezone_name: str = "America/New_York"):
    return decide_contextual_meal_photo(MealPhotoCandidate(
        origin="chat",
        semantic_intent=MealPhotoSemanticIntent.IMPLICIT_CAPTURE,
        classification="food",
        recognition_confidence=0.93,
        reference_now=at,
        timezone_name=timezone_name,
        idempotency_clear=True,
    ))


def _vision_result():
    return {
        "foods": [{
            "name": "鸡胸肉",
            "quantity": "约120g",
            "calories": 198,
            "protein": 37.0,
            "carbs": 0.0,
            "fat": 4.3,
            "fiber": 0.0,
            "confidence": 0.93,
        }],
        "total_calories": 198,
        "total_protein": 37.0,
        "total_carbs": 0.0,
        "total_fat": 4.3,
        "total_fiber": 0.0,
        "health_tips": "营养估算，仅供参考。",
    }


def _source_image(tmp_path, monkeypatch, user_id: int) -> str:
    from app.api import upload as upload_api

    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path / "chat"))
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path / "uploads"))
    return chat_utils.upload_chat_image(VALID_PNG_BASE64, user_id, "png")


def test_auto_capture_copies_owned_chat_media_to_one_idempotent_diet_record(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=701,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    first = service.capture(capture)
    retry = service.capture(capture)

    assert first.record is not None
    assert retry.record is not None
    assert retry.record.id == first.record.id
    assert retry.replayed is True
    assert db.query(DietRecord).count() == 1
    asset = db.query(DietPhotoAsset).one()
    assert asset.user_id == test_user.id
    assert asset.diet_record_id == first.record.id
    assert asset.photo_draft_token is None
    assert asset.lifecycle == "attached"
    assert asset.storage_key.startswith(f"/api/v1/upload/files/diet/{test_user.id}/")
    assert "?" not in asset.storage_key
    assert first.record.image_url == asset.storage_key


def test_auto_capture_creates_the_same_postmeal_protocol_once(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    calls = []

    def create_protocol(db_session, user_id, **kwargs):
        calls.append((db_session, user_id, kwargs))
        return None

    monkeypatch.setattr(
        "app.services.health_protocol_service.create_postmeal_walk_protocol",
        create_protocol,
    )
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=704,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    first = service.capture(capture)
    retry = service.capture(capture)

    assert first.record is not None
    assert retry.replayed is True
    assert calls == [(
        db,
        test_user.id,
        {
            "record_date": first.record.record_date,
            "meal_type": "lunch",
            "meal_time": first.record.meal_time,
            "diet_record_id": first.record.id,
        },
    )]


def test_food_photo_outside_auto_window_creates_owner_bound_confirmation_draft(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=702,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    result = service.capture(capture)

    assert result.record is None
    assert result.photo_draft is not None
    assert db.query(DietRecord).count() == 0
    draft = db.query(DietPhotoDraft).one()
    asset = db.query(DietPhotoAsset).one()
    assert draft.token == result.photo_draft.token
    assert asset.photo_draft_token == draft.token
    assert asset.diet_record_id is None
    assert asset.lifecycle == "pending"


def test_capture_rejects_a_chat_image_not_owned_by_the_target_user(
    db, test_user, tmp_path, monkeypatch
):
    source_url = _source_image(tmp_path, monkeypatch, test_user.id + 99)
    service = ContextualMealPhotoService(db)
    capture = ContextualMealPhotoCapture(
        user_id=test_user.id,
        source_message_id=703,
        source_image_url=source_url,
        source_image_index=0,
        decision=_decision(at=datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)),
        vision_result=_vision_result(),
    )

    with pytest.raises(ContextualMealPhotoServiceError, match="owned_chat_image"):
        service.capture(capture)

    assert db.query(DietRecord).count() == 0
    assert db.query(DietPhotoAsset).count() == 0
