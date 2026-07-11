import pytest

from app.config import settings
from app.models.food_nutrition import FoodItem, FoodNutrient
from app.services.agent_executor import AgentExecutor


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
    assert executor._should_preprocess_attached_images(1, "看看这张风景照片") is False
