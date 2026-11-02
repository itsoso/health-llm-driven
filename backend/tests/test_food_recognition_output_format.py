"""Output formatting must not remove recognition rules or alter write authority."""
import asyncio
import json
import re

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
    reverse = {v: k for k, v in food.FOOD_RECOGNITION_WIRE_KEYS.items()}
    restored = re.sub(r"\b(" + "|".join(reverse) + r")\b", lambda m: reverse[m.group()], prompt)
    assert restored == food.FOOD_RECOGNITION_SYSTEM_PROMPT + "\n" + food.FOOD_RECOGNITION_OUTPUT_FORMAT
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


@pytest.mark.parametrize("method", ["recognize_food_from_base64", "recognize_food_from_url"])
@pytest.mark.parametrize("wire", [False, True])
def test_wire_format_restores_label_values_before_sanitizing(method, wire):
    canonical = {"foods": [{
        "name": "合成标签", "quantity": "每100g", "quantity_grams": 100,
        "label_basis_grams": 100, "calories": 380, "protein": 12,
        "carbs": 60, "fat": 8, "fiber": None, "confidence": .95,
        "portion_confidence": None, "source": "nutrition_label",
        "nutrition_basis": "nutrition_label_per_100g",
    }], "meal_description": "标签", "health_tips": "未确认食用量"}
    payload = dict(canonical)
    if wire:
        keys = food.FOOD_RECOGNITION_WIRE_KEYS
        payload = {keys.get(k,k): v for k,v in canonical.items()}
        payload["foods"] = [{keys.get(k,k): v for k,v in canonical["foods"][0].items()}]

    class Provider:
        model = "qwen3.8-flash"
        async def chat_with_vision(self, **kwargs):
            assert kwargs["extra_body"]["enable_thinking"] is False
            return "```json\n" + json.dumps(payload) + "\n```"

    service = food.FoodRecognitionService()
    service._provider = Provider()
    actual = asyncio.run(getattr(service, method)("synthetic-image"))
    assert actual == food.sanitize_food_recognition_result(canonical)


@pytest.mark.parametrize("payload", [
    {"foods": [], "meal": "a", "meal_description": "b"},
    {"foods": [{"portion": "1个", "quantity": "2个"}]},
])
def test_wire_format_rejects_ambiguous_aliases(payload):
    with pytest.raises(ValueError, match="ambiguous food wire field"):
        food._expand_food_recognition_wire_payload(payload)


def test_wire_expansion_does_not_modify_values_or_unrelated_nested_metadata():
    original = {"foods": [{"name": "portion", "grams": None, "metadata": {"grams": 90}}],
                "meal": "conf portion grams", "metadata": {"meal": "unaltered"}}
    expanded = food._expand_food_recognition_wire_payload(original)
    assert expanded["foods"][0] == {"name": "portion", "quantity_grams": None,
                                    "metadata": {"grams": 90}}
    assert expanded["meal_description"] == "conf portion grams"
    assert expanded["metadata"] == {"meal": "unaltered"}
    assert "grams" in original["foods"][0]


@pytest.mark.parametrize("method", ["recognize_food_from_base64", "recognize_food_from_url"])
def test_wire_collision_never_returns_a_recordable_food(method):
    class Provider:
        model = "qwen3.8-flash"
        async def chat_with_vision(self, **kwargs):
            return json.dumps({"foods": [{"name": "苹果", "quantity": "1个",
                                          "portion": "2个", "calories": 80}]})

    service = food.FoodRecognitionService()
    service._provider = Provider()
    result = asyncio.run(getattr(service, method)("synthetic-image"))
    assert result["success"] is False
    assert result["foods"] == []


@pytest.mark.parametrize("method", ["recognize_food_from_base64", "recognize_food_from_url"])
@pytest.mark.parametrize("model,structured", [("qwen3.8-flash", True),
                                               ("qwen-vl-max", False),
                                               ("qwen3-vl-flash", False)])
def test_json_mode_is_bound_to_the_measured_vision_model(method, model, structured):
    calls = []

    class Provider:
        async def chat_with_vision(self, **kwargs):
            calls.append(kwargs)
            return json.dumps({"foods": [{"name": "苹果", "portion": "1个",
                                          "grams": None, "calories": None}],
                               "meal": "苹果", "tips": None})

    provider = Provider()
    provider.model = model
    service = food.FoodRecognitionService()
    service._provider = provider
    result = asyncio.run(getattr(service, method)("synthetic-image"))
    if structured:
        assert calls[0]["response_format"] == {"type": "json_object"}
    else:
        assert "response_format" not in calls[0]
    assert calls[0]["temperature"] == 0.1
    assert calls[0]["max_tokens"] == 2000
    assert calls[0]["messages"][0]["content"] == food._food_recognition_request_prompt(provider)
    assert result["success"] is True
    assert result["foods"][0]["calories"] is None
    assert result["foods"][0].get("quantity_grams") is None


@pytest.mark.parametrize("method", ["recognize_food_from_base64", "recognize_food_from_url"])
def test_json_mode_rejection_does_not_retry_without_the_contract(method):
    calls = []

    class Provider:
        model = "qwen3.8-flash"

        async def chat_with_vision(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("request rejected")

    service = food.FoodRecognitionService()
    service._provider = Provider()
    result = asyncio.run(getattr(service, method)("synthetic-image"))
    assert result["success"] is False
    assert result["foods"] == []
    assert len(calls) == 1
    assert calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("method", ["recognize_food_from_base64", "recognize_food_from_url"])
@pytest.mark.parametrize("model", ["qwen3.8-flash", "qwen-vl-max", "qwen3-vl-flash"])
def test_derived_description_is_skipped_only_for_the_measured_model(method, model):
    calls = []

    class Provider:
        async def chat_with_vision(self, **kwargs):
            calls.append(kwargs)
            return json.dumps({"foods": [{"name": "牛奶", "portion": "1盒",
                                          "source": "order_estimate", "basis": "order_estimate",
                                          "grams": None, "calories": None}],
                               "meal": None, "tips": "份量待核对"})

    provider = Provider()
    provider.model = model
    service = food.FoodRecognitionService()
    service._provider = provider
    result = asyncio.run(getattr(service, method)("synthetic-image"))
    prompt = calls[0]["messages"][0]["content"]
    suffix = "\nmeal 固定为 null，餐食简述由应用根据 foods 生成；不重复生成。"
    if model == "qwen3.8-flash":
        assert prompt.endswith(suffix)
        assert '"meal": null' in prompt
        restored = prompt.removesuffix(suffix).replace('"meal": null', '"meal": "餐食简述"')
        assert restored == food._food_recognition_request_prompt()
    else:
        assert prompt == food._food_recognition_request_prompt()
    assert result["meal_description"] == "牛奶 1盒"
    assert result["health_tips"] == "份量待核对"
    assert result["foods"][0]["portion_basis"] == "order_quantity"
    assert result["foods"][0]["nutrition_basis"] == "order_estimate"
    assert result["foods"][0]["calories"] is None
    assert result["foods"][0].get("quantity_grams") is None
