import json
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.models.food_nutrition import FoodItem, FoodNutrient
from app.models.daily_health import DietRecord
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.agent_executor import (
    AgentExecutor,
    _contextual_meal_consumed_fraction,
    _write_receipt_from_tool_result,
)
from app.services.dynamic_card_persistence import cards_for_persistence
from app.services import chat_utils


VALID_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z/QAAAABJRU5ErkJggg=="


def _food_result():
    return {
        "success": True,
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
    }


def _food_photo_executor(db, tmp_path, monkeypatch):
    from app.api import upload as upload_api

    user = User(
        username="agent_food_photo",
        email="agent-food-photo@example.com",
        hashed_password="hashed_password",
        name="Agent 食物照片用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserProfile(user_id=user.id, manual_timezone="America/New_York"))
    db.commit()
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path / "chat"))
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path / "uploads"))
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_source_message_id = 888
    executor._current_turn_image_urls = [
        chat_utils.upload_chat_image(VALID_PNG_BASE64, user.id, "png")
    ]
    executor._agent_kernel_reference_now = lambda: datetime(2026, 7, 19, 16, 30, tzinfo=timezone.utc)
    return executor, user


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("记录这餐，吃了三分之一", (1 / 3, "三分之一")),
        ("这份只吃了1/3", (1 / 3, "1/3")),
        ("这餐应该只吃三分之一吗？", None),
        ("记录这餐，吃了三分之一的蛋糕", None),
        ("吃了三分之一的蛋糕", None),
    ],
)
def test_contextual_meal_fraction_only_scales_an_explicit_whole_meal(
    message, expected
):
    parsed = _contextual_meal_consumed_fraction(message)
    if expected is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert parsed[0] == pytest.approx(expected[0])
        assert parsed[1] == expected[1]


def test_agent_auto_captures_empty_high_confidence_lunch_photo_with_receipt(
    db, tmp_path, monkeypatch
):
    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)

    result = executor._capture_contextual_meal_photo("", _food_result(), image_index=0)

    assert result is not None
    assert result.record is not None
    assert result.record.user_id == user.id
    assert db.query(DietRecord).count() == 1
    assert executor._turn_contextual_diet_receipts == [{
        "operation_id": f"contextual_meal_photo:{result.record.id}",
        "status": "verified",
        "resource_type": "diet_record",
        "resource_id": str(result.record.id),
        "verified": True,
    }]
    card = executor._turn_contextual_diet_cards[0]
    assert card["type"] == "diet_draft"
    assert card["data"]["recorded"] is True
    assert card["data"]["record_id"] == result.record.id
    adjust_action = card["actions"][0]
    assert adjust_action["action"] == "ui.inline.expand"
    assert adjust_action["label"] == "调整记录"
    assert adjust_action["payload"]["target"] == "adjust_record"
    assert adjust_action["payload"]["patch"]["adjust_record"] == {
        "record_id": result.record.id,
        "meal_type": "lunch",
        "food_items": result.record.food_items,
        "calories": result.record.calories,
        "protein": result.record.protein,
        "carbs": result.record.carbs,
        "fat": result.record.fat,
    }
    assert "photo_url" not in cards_for_persistence([card])[0]["data"]


def test_agent_analysis_intent_never_auto_captures_food_photo(db, tmp_path, monkeypatch):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)

    result = executor._capture_contextual_meal_photo("请分析这张图片", _food_result(), image_index=0)

    assert result is None
    assert db.query(DietRecord).count() == 0
    prompt_context = executor._format_food_recognition_for_agent(
        "请分析这张图片", _food_result(), contextual_capture=result,
    )
    assert "严禁调用 health_record" in prompt_context


def test_agent_creates_owner_bound_confirmation_card_outside_meal_window(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    executor._agent_kernel_reference_now = lambda: datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)

    result = executor._capture_contextual_meal_photo("", _food_result(), image_index=0)

    assert result is not None
    assert result.record is None
    assert result.photo_draft is not None
    card = executor._turn_contextual_diet_cards[0]
    assert card["type"] == "diet_draft"
    assert card["data"]["photo_asset_id"]
    assert "signature=" in card["data"]["photo_url"]
    # Dynamic-card data is user-facing. Keep its number representation aligned
    # with the product display contract, while the action payload keeps raw data.
    assert isinstance(card["data"]["protein"], int)
    assert card["data"]["protein"] == 37
    assert isinstance(card["data"]["fiber"], int)
    assert card["data"]["fiber"] == 0
    action = card["actions"][0]
    assert action["action"] == "diet_record.create"
    assert action["payload"]["record"]["protein"] == 37.0
    assert action["payload"]["record"]["source"] == "chat_photo"
    assert action["payload"]["record"]["photo_draft_token"] == result.photo_draft.token
    assert "photo_url" not in cards_for_persistence([card])[0]["data"]


def test_agent_explicit_food_photo_write_records_outside_meal_window(
    db, tmp_path, monkeypatch
):
    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    executor._agent_kernel_reference_now = lambda: datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)

    result = executor._capture_contextual_meal_photo("记录这餐", _food_result(), image_index=0)

    assert result is not None
    assert result.record is not None
    assert result.record.user_id == user.id
    assert result.record.meal_type == "snack"
    assert db.query(DietRecord).count() == 1
    assert executor._turn_contextual_diet_receipts == [{
        "operation_id": f"contextual_meal_photo:{result.record.id}",
        "status": "verified",
        "resource_type": "diet_record",
        "resource_id": str(result.record.id),
        "verified": True,
    }]
    card = executor._turn_contextual_diet_cards[0]
    assert card["data"]["recorded"] is True
    assert card["actions"][0]["action"] == "ui.inline.expand"


@pytest.mark.asyncio
async def test_agent_applies_consumed_fraction_before_contextual_photo_write(
    db, tmp_path, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)

    async def recognize(*_args, **_kwargs):
        return _food_result()

    monkeypatch.setattr(
        food_recognition_service,
        "recognize_food_from_base64",
        recognize,
    )

    context = await executor._analyze_food_images_with_structured_vision(
        "记录这餐，吃了三分之一",
        [{"base64": VALID_PNG_BASE64, "type": "png"}],
    )

    records = db.query(DietRecord).filter(DietRecord.user_id == user.id).all()
    assert len(records) == 1
    record = records[0]
    assert record.calories == pytest.approx(66)
    assert record.protein == pytest.approx(12.3)
    assert record.fat == pytest.approx(1.4)
    assert "按实际食用三分之一计" in record.food_items
    assert executor._turn_contextual_diet_consumed_fraction == pytest.approx(1 / 3)
    assert len(executor._turn_contextual_diet_receipts) == 1
    assert len(executor._turn_contextual_diet_cards) == 1
    assert context is not None
    assert "份量已在首次写入中按三分之一修正" in context
    assert "不要再次调用 health_record 或 health_manage 写入" in context


@pytest.mark.asyncio
async def test_contextual_fraction_update_replays_receipt_without_second_write(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    capture = executor._capture_contextual_meal_photo(
        "记录这餐",
        _food_result(),
        image_index=0,
    )
    assert capture is not None
    assert capture.record is not None
    executor._turn_contextual_diet_consumed_fraction = 1 / 3

    async def unexpected_put(*_args, **_kwargs):
        raise AssertionError("same-turn contextual diet update must not reach the API")

    monkeypatch.setattr(executor, "_api_put", unexpected_put)

    update_args = {
        "record_type": "diet",
        "operation": "update",
        "record_id": capture.record.id,
        "data": {"calories": 22},
    }
    result = await executor._exec_health_manage(
        "https://health.example.test",
        {"Authorization": "Bearer test"},
        update_args,
    )

    payload = json.loads(result)
    assert payload == {
        "id": capture.record.id,
        "record_id": capture.record.id,
        "resource_type": "diet_record",
        "operation_id": f"contextual_meal_photo:{capture.record.id}",
        "status": "recorded",
        "replayed": True,
        "portion_adjustment_applied": True,
    }
    receipt = _write_receipt_from_tool_result(
        "health_manage",
        update_args,
        result,
    )
    assert receipt is not None
    assert receipt["operation_id"] == (
        f"contextual_meal_photo:{capture.record.id}"
    )
    assert receipt["status"] == "verified"
    db.refresh(capture.record)
    assert capture.record.calories == pytest.approx(198)


def test_agent_auto_capture_failure_surfaces_the_recoverable_confirmation_card(
    db, tmp_path, monkeypatch
):
    executor, _user = _food_photo_executor(db, tmp_path, monkeypatch)
    real_commit = db.commit
    commits = 0

    def fail_first_capture_commit():
        nonlocal commits
        commits += 1
        if commits == 1:
            raise RuntimeError("simulated automatic record write failure")
        return real_commit()

    monkeypatch.setattr(db, "commit", fail_first_capture_commit)
    result = executor._capture_contextual_meal_photo("", _food_result(), image_index=0)

    assert result is not None
    assert result.record is None
    assert result.photo_draft is not None
    card = executor._turn_contextual_diet_cards[0]
    assert card["type"] == "diet_draft"
    assert card["data"]["auto_save_fallback"] is True
    assert card["actions"][0]["action"] == "diet_record.create"


@pytest.mark.asyncio
async def test_structured_food_vision_calibrates_before_building_agent_context(
    db, monkeypatch
):
    from app.services.ai.food_recognition import food_recognition_service

    db.add(FoodItem(
        food_id="cfc:chicken_breast",
        canonical_name="鸡胸肉",
        aliases=["鸡肉"],
        calibration_names=["鸡胸肉"],
        locale="zh-CN",
        source="china_food_composition",
        source_ref="test-fixture",
    ))
    db.add(FoodNutrient(
        food_id="cfc:chicken_breast",
        kcal_per_100g=165.0,
        protein_g_per_100g=31.0,
        carbs_g_per_100g=0.0,
        fat_g_per_100g=3.6,
        fiber_g_per_100g=0.0,
        source="china_food_composition",
        source_ref="test-fixture",
    ))
    db.commit()

    async def recognize(*_args, **_kwargs):
        return {
            "success": True,
            "foods": [{
                "name": "鸡胸肉",
                "quantity": "200g",
                "calories": 999,
                "protein": 1,
                "carbs": 50,
                "fat": 40,
                "fiber": 8,
                "confidence": 0.9,
            }],
            "total_calories": 999,
            "total_protein": 1,
            "total_carbs": 50,
            "total_fat": 40,
            "total_fiber": 8,
        }

    monkeypatch.setattr(food_recognition_service, "recognize_food_from_base64", recognize)

    context = await AgentExecutor(db)._analyze_food_images_with_structured_vision(
        "记录午餐",
        [{"base64": "ZmFrZQ==", "type": "jpeg"}],
    )

    assert context is not None
    assert "鸡胸肉 200g 约330kcal" in context
    assert '"food_id": "cfc:chicken_breast"' in context
    assert '"source": "china_food_composition"' in context
    assert '"ai_recognized": 1' in context


@pytest.mark.asyncio
async def test_generic_vision_fallback_does_not_repeat_structured_recognition(
    db, monkeypatch
):
    executor = AgentExecutor(db)
    calls = 0

    async def no_structured_result(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return None

    class FailedResponse:
        status_code = 503
        text = "unavailable"

    class FakeHttpClient:
        async def post(self, *_args, **_kwargs):
            return FailedResponse()

    monkeypatch.setattr(executor, "_analyze_food_images_with_structured_vision", no_structured_result)
    monkeypatch.setattr(settings, "llm_vision_base_url", "https://vision.example.test")
    monkeypatch.setattr(settings, "llm_vision_api_key", "test-key")
    executor._http_client = FakeHttpClient()

    result = await executor._analyze_image_with_vision(
        "帮我看看",
        [{"base64": "ZmFrZQ==", "type": "jpeg"}],
    )

    assert result is None
    assert calls == 1


def test_commercial_multimodal_food_photos_still_use_structured_preprocessing(
    db, monkeypatch
):
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_should_send_raw_images_to_primary_model", lambda _user_id: True)

    assert executor._should_preprocess_attached_images(1, "记录这张午餐照片") is True
    assert executor._should_preprocess_attached_images(1, "请分析这些图片") is True
    assert executor._should_preprocess_attached_images(1, "帮我记一下") is True
    assert executor._should_preprocess_attached_images(1, "拍照记餐") is True
    assert executor._should_preprocess_attached_images(1, "看看这张风景照片") is False


def test_explicit_aigc_photo_request_never_enters_food_preprocessing(db, monkeypatch):
    """A creative request must not turn an attached image into a diet candidate."""
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_should_send_raw_images_to_primary_model", lambda _user_id: False)

    assert executor._should_preprocess_attached_images(
        1,
        "基于这张照片生成今天活动的短视频，以此照片为开头。",
    ) is False
