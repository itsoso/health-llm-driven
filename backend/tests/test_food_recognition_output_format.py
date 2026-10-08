"""Output formatting must not remove recognition rules or alter write authority."""
import asyncio
import json

import pytest
from app.services.ai import food_recognition as food


@pytest.mark.parametrize("method", ["recognize_food_from_base64", "recognize_food_from_url"])
def test_visual_requests_keep_full_policy_and_request_compact_json(method):
    captured = []
    response = {
        "foods": [{
            "name": "苹果", "quantity": "1个", "quantity_grams": None,
            "label_basis_grams": None, "calories": 80, "protein": 0.5,
            "carbs": 20, "fat": 0.3, "fiber": 2, "confidence": 0.8,
            "portion_confidence": 0.6, "source": "vision_estimate",
            "nutrition_basis": "vision_estimate",
        }], "meal_description": "水果", "health_tips": "份量待核对",
    }

    class Provider:
        model = "qwen-vl-max"

        async def chat_with_vision(self, **kwargs):
            captured.append(kwargs)
            return json.dumps(response, ensure_ascii=False, separators=(",", ":"))

    service = food.FoodRecognitionService()
    service._provider = Provider()
    result = asyncio.run(getattr(service, method)("synthetic-image"))
    request = captured[0]
    prompt = request["messages"][0]["content"]
    assert prompt.startswith(food.FOOD_RECOGNITION_SYSTEM_PROMPT + "\n")
    assert "单行紧凑格式" in prompt
    assert "保留全部要求的字段与规则" in prompt
    assert request["temperature"] == 0.1
    assert request["max_tokens"] == 2000
    assert "model" not in request
    assert result["success"] is True
    # The existing sanitizer omits absent/unknown mass, never turns it into 0.
    assert result["foods"][0].get("quantity_grams") is None
    assert result["foods"][0]["nutrition_basis"] == "vision_estimate"
    assert result["foods"][0]["calories"] == 80


@pytest.mark.parametrize("indent", [None, 2])
def test_formatting_preserves_unknowns_and_label_basis(indent):
    result = {
        "foods": [{
            "name": "合成燕麦片", "quantity": "每100g", "quantity_grams": 100,
            "label_basis_grams": 100, "calories": 380, "protein": 12,
            "carbs": 60, "fat": 8, "fiber": None, "confidence": 0.95,
            "portion_confidence": None, "source": "nutrition_label",
            "nutrition_basis": "nutrition_label_per_100g",
        }], "meal_description": "营养标签", "health_tips": "实际食用量未知",
    }
    compact = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    formatted = json.dumps(result, ensure_ascii=False, indent=indent)
    assert food.sanitize_food_recognition_result(json.loads(compact)) == (
        food.sanitize_food_recognition_result(json.loads(formatted))
    )
