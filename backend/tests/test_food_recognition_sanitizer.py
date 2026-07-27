import json
import logging

import pytest

from app.services.ai.food_recognition import (
    FoodRecognitionService,
    apply_user_stated_amount_to_nutrition_label,
    merge_food_recognition_results,
    sanitize_food_recognition_result,
)
from app.config import Settings


def test_default_vision_model_uses_current_fast_food_recognition_model():
    assert Settings.model_fields["llm_vision_model"].default == "qwen3-vl-flash"


def test_sanitize_food_recognition_rejects_ui_card_copy():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [
            {
                "name": "和午餐食品营养卡",
                "quantity": "",
                "calories": 0,
                "protein": 0,
                "carbs": 0,
                "fat": 0,
            }
        ],
        "meal_description": "和午餐食品营养卡",
        "total_calories": 0,
        "total_protein": 0,
        "total_carbs": 0,
        "total_fat": 0,
    })

    assert result["success"] is False
    assert result["foods"] == []
    assert "未识别到可记录的食物" in result["error"]


def test_sanitize_food_recognition_preserves_safe_operational_error():
    result = sanitize_food_recognition_result({
        "success": False,
        "error": "识别超时，请重试",
        "foods": [],
    })

    assert result["success"] is False
    assert result["error"] == "识别超时，请重试"


def test_sanitize_food_recognition_keeps_real_food_and_recomputes_totals():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [
            {"name": "今日饮食", "calories": 0, "protein": 0, "carbs": 0, "fat": 0},
            {
                "name": "鸡胸肉",
                "quantity": "200g",
                "calories": 330,
                "protein": 62,
                "carbs": 0,
                "fat": 7,
                "fiber": 2.4,
            },
        ],
        "meal_description": "今日饮食营养卡",
        "total_calories": 999,
        "total_protein": 99,
        "total_carbs": 88,
        "total_fat": 77,
        "total_fiber": 66,
    })

    assert result["success"] is True
    assert [food["name"] for food in result["foods"]] == ["鸡胸肉"]
    assert result["total_calories"] == 330
    assert result["total_protein"] == 62
    assert result["total_carbs"] == 0
    assert result["total_fat"] == 7
    assert result["total_fiber"] == 2.4
    assert result["meal_description"] == "鸡胸肉 200g"
    assert result["foods"][0]["portion_basis"] == "vision_estimate"


def test_sanitize_food_recognition_does_not_keep_stale_totals_for_unknown_nutrients():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [
            {
                "name": "鸡胸肉",
                "quantity": "200g",
                "calories": 330,
                "protein": None,
                "carbs": 0,
                "fat": 7,
            }
        ],
        "total_calories": 999,
        "total_protein": 99,
        "total_carbs": 88,
        "total_fat": 77,
    })

    assert result["total_calories"] == 330
    assert result["total_protein"] is None
    assert result["total_carbs"] == 0
    assert result["total_fat"] == 7


def test_sanitize_food_recognition_rejects_non_food_intake_but_keeps_meal_items():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [
            {"name": "牛肉面", "quantity": "1碗", "calories": 620},
            {"name": "奥美拉唑肠溶片", "quantity": "1片", "calories": 0},
            {"name": "鱼油", "quantity": "2粒", "calories": 18},
        ],
    })

    assert result["success"] is True
    assert [food["name"] for food in result["foods"]] == ["牛肉面"]
    assert result["meal_description"] == "牛肉面 1碗"


def test_sanitize_food_recognition_keeps_food_with_supplement_like_name():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [{
            "name": "益生菌酸奶",
            "quantity": "1杯",
            "calories": 130,
        }],
    })

    assert result["success"] is True
    assert [food["name"] for food in result["foods"]] == ["益生菌酸奶"]


def test_sanitize_food_recognition_normalizes_untrusted_numbers_and_portion_truth():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [
            {
                "name": "鸡胸肉",
                "quantity": "200g",
                "calories": 330,
                "protein": -4,
                "carbs": "not-a-number",
                "fat": 7.2,
                "fiber": 0,
                "confidence": 1.4,
                "portion_confidence": "0.72",
            },
            {
                "name": "西兰花",
                "quantity": None,
                "calories": 50,
                "protein": 4,
                "carbs": 8,
                "fat": 0.5,
                "fiber": 4,
                "confidence": 0.88,
                "portion_confidence": -1,
            },
        ],
    })

    chicken, broccoli = result["foods"]
    assert chicken["protein"] is None
    assert chicken["carbs"] is None
    assert chicken["confidence"] is None
    assert chicken["portion_basis"] == "vision_estimate"
    assert chicken["portion_confidence"] == 0.72
    assert broccoli["portion_basis"] == "unknown"
    assert broccoli["portion_confidence"] is None
    assert result["total_protein"] is None
    assert result["total_carbs"] is None


def test_sanitize_food_recognition_deduplicates_and_caps_model_items():
    foods = [
        {"name": "鸡胸肉", "quantity": "200g", "calories": 330},
        {"name": " 鸡胸肉 ", "quantity": " 200g ", "calories": 999},
    ]
    foods.extend(
        {"name": f"配菜{i}", "quantity": "1份", "calories": i}
        for i in range(20)
    )

    result = sanitize_food_recognition_result({"success": True, "foods": foods})

    assert len(result["foods"]) == 12
    assert [food["name"] for food in result["foods"]].count("鸡胸肉") == 1
    assert result["foods"][0]["calories"] == 330


def test_legacy_generic_nutrition_label_is_scaled_from_local_user_amount():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [{
            "name": "每日坚果",
            "quantity": "每100g",
            "quantity_grams": 100,
            "calories": 655,
            "protein": 15,
            "carbs": 15,
            "fat": 60,
            "fiber": 7.5,
            "confidence": 0.95,
            "source": "nutrition_label",
            "nutrition_basis": "nutrition_label",
        }],
    })

    scaled = apply_user_stated_amount_to_nutrition_label(
        result,
        "记录这餐，吃了20克坚果",
    )
    scaled = sanitize_food_recognition_result(scaled)

    assert scaled["foods"][0]["quantity"] == "20g"
    assert scaled["foods"][0]["calories"] == 131
    assert scaled["foods"][0]["protein"] == 3
    assert scaled["foods"][0]["nutrition_basis"] == "nutrition_label_scaled"


@pytest.mark.asyncio
async def test_food_recognition_does_not_log_model_content_or_food_names(caplog):
    private_food_name = "仅用于隐私测试的私密餐食"

    class FakeProvider:
        async def chat_with_vision(self, **_kwargs):
            return json.dumps({
                "foods": [{
                    "name": private_food_name,
                    "quantity": "1份",
                    "calories": 420,
                }],
            }, ensure_ascii=False)

    service = FoodRecognitionService()
    service._provider = FakeProvider()

    with caplog.at_level(logging.INFO, logger="app.services.ai.food_recognition"):
        result = await service.recognize_food_from_base64("aW1hZ2U=")

    assert result["success"] is True
    assert private_food_name not in caplog.text


@pytest.mark.asyncio
async def test_food_recognition_disables_thinking_for_qwen3_vision_models():
    class FakeProvider:
        model = "qwen3-vl-flash"

        def __init__(self):
            self.kwargs = None

        async def chat_with_vision(self, **kwargs):
            self.kwargs = kwargs
            return json.dumps({
                "foods": [{
                    "name": "鸡肉块",
                    "quantity": "1份",
                    "calories": 320,
                }],
            }, ensure_ascii=False)

    provider = FakeProvider()
    service = FoodRecognitionService()
    service._provider = provider

    result = await service.recognize_food_from_base64("aW1hZ2U=")

    assert result["success"] is True
    assert provider.kwargs["extra_body"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_food_recognition_requests_machine_readable_nutrition_label_basis():
    class FakeProvider:
        def __init__(self):
            self.kwargs = None

        async def chat_with_vision(self, **kwargs):
            self.kwargs = kwargs
            return json.dumps({
                "foods": [{
                    "name": "每日坚果",
                    "quantity": "每100g",
                    "quantity_grams": 100,
                    "label_basis_grams": 100,
                    "calories": 655,
                    "protein": 15,
                    "carbs": 15,
                    "fat": 60,
                    "fiber": 7.5,
                    "confidence": 0.95,
                    "source": "nutrition_label",
                    "nutrition_basis": "nutrition_label_per_100g",
                }],
            }, ensure_ascii=False)

    provider = FakeProvider()
    service = FoodRecognitionService()
    service._provider = provider

    result = await service.recognize_food_from_base64("aW1hZ2U=")

    assert result["success"] is True
    assert result["foods"][0]["label_basis_grams"] == 100
    system_prompt = provider.kwargs["messages"][0]["content"]
    assert "营养成分表" in system_prompt
    assert "nutrition_label_per_100g" in system_prompt


@pytest.mark.asyncio
async def test_food_recognition_does_not_expose_provider_error_content(caplog):
    private_error = "provider-error-containing-private-meal"

    class FailingProvider:
        async def chat_with_vision(self, **_kwargs):
            raise RuntimeError(private_error)

    service = FoodRecognitionService()
    service._provider = FailingProvider()

    with caplog.at_level(logging.ERROR, logger="app.services.ai.food_recognition"):
        result = await service.recognize_food_from_base64("aW1hZ2U=")

    assert result["success"] is False
    assert private_error not in result["error"]
    assert private_error not in caplog.text


def test_multi_photo_same_dish_is_ambiguous_and_requires_confirmation():
    merged = merge_food_recognition_results([
        {
            "success": True,
            "foods": [{
                "name": "煎饼",
                "quantity": "约4块",
                "calories": 360,
                "protein": 12,
                "confidence": 0.91,
            }],
        },
        {
            "success": True,
            "foods": [{
                "name": "煎饼",
                "quantity": "约4块",
                "calories": 360,
                "protein": 12,
                "confidence": 0.88,
            }],
        },
    ])

    assert merged["success"] is True
    assert len(merged["foods"]) == 1
    assert merged["total_calories"] == 360
    assert merged["total_protein"] == 12
    assert merged["multi_photo_conflict"] is True
    assert merged["multi_photo_ambiguous_duplicate"] is True


def test_multi_photo_results_flag_conflicting_portions_for_confirmation():
    merged = merge_food_recognition_results([
        {
            "success": True,
            "foods": [{
                "name": "煎饼",
                "quantity": "约2块",
                "calories": 180,
                "confidence": 0.91,
            }],
        },
        {
            "success": True,
            "foods": [{
                "name": "煎饼",
                "quantity": "约4块",
                "calories": 360,
                "confidence": 0.89,
            }],
        },
    ])

    assert merged["success"] is True
    assert merged["multi_photo_conflict"] is True


def test_multi_photo_results_preserve_consumed_fraction_context():
    source = {
        "success": True,
        "foods": [{
            "name": "鸡胸肉",
            "quantity": "约40g",
            "calories": 66,
            "protein": 12.3,
            "carbs": 0,
            "fat": 1.4,
            "fiber": 0,
        }],
        "consumed_fraction": 1 / 3,
        "consumed_fraction_label": "三分之一",
    }

    merged = merge_food_recognition_results([source])

    assert merged["consumed_fraction"] == pytest.approx(1 / 3)
    assert merged["consumed_fraction_label"] == "三分之一"
    assert merged["foods"][0]["quantity"] == "约40g"
