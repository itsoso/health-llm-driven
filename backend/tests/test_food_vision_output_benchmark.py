"""The speed comparison must retain malformed, missing-food and unsafe results."""
import asyncio
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "food_vision_output_benchmark",
    Path(__file__).resolve().parents[2] / "scripts/benchmark_food_vision_output.py",
)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def response():
    return {"foods": [{
        "name": "合成燕麦片", "quantity": "每100g", "quantity_grams": 100,
        "label_basis_grams": 100, "calories": 380, "protein": 12, "carbs": 60,
        "fat": 8, "fiber": None, "confidence": 0.9, "portion_confidence": None,
        "source": "nutrition_label", "nutrition_basis": "nutrition_label_per_100g",
    }], "meal_description": "营养标签", "health_tips": "实际食用量未知"}


def test_candidate_replay_matches_runtime_prompt_exactly():
    from app.services.ai import food_recognition as food

    assert benchmark.COMPACT_FORMAT == food.FOOD_RECOGNITION_OUTPUT_FORMAT
    assert food._food_recognition_request_prompt() == (
        food.FOOD_RECOGNITION_SYSTEM_PROMPT + "\n" + benchmark.COMPACT_FORMAT
    )


EXPECTED = {"food_count": 1, "food_name_patterns": ["燕麦"], "exact_food_values": [
    {"index": 0, "values": {"quantity_grams": 100, "calories": 380, "fiber": None,
                             "nutrition_basis": "nutrition_label_per_100g"}},
]}


@pytest.mark.parametrize("indent", [None, 2])
def test_whitespace_is_not_a_quality_failure(indent):
    assert benchmark.check_response(json.dumps(response(), indent=indent), EXPECTED) == []


@pytest.mark.parametrize("fault", ["missing", "wrong_value", "false_success", "empty", "invalid_number", "wrong_name", "unknown_to_zero"])
def test_real_contract_regressions_fail(fault):
    value = deepcopy(response())
    food = value["foods"][0]
    if fault == "missing":
        del food["portion_confidence"]
    elif fault == "wrong_value":
        food["calories"] = 20
    elif fault == "false_success":
        value["health_tips"] = "已记录这餐"
    elif fault == "empty":
        value["foods"] = []
    elif fault == "invalid_number":
        food["protein"] = float("nan")
    elif fault == "unknown_to_zero":
        food["fiber"] = 0
    else:
        food["name"] = "按钮"
    assert benchmark.check_response(json.dumps(value), EXPECTED)


def test_failure_is_counted_even_when_it_returns_faster():
    rows = [{"variant": "compact", "api_success": True, "latency_ms": 100,
             "completion_tokens": 10, "failures": ["wrong_food_count"]},
            {"variant": "compact", "api_success": False, "latency_ms": 10,
             "failures": ["api_or_evaluation_failure"]}]
    summary = benchmark.summarize(rows)["compact"]
    assert summary["attempts"] == 2
    assert summary["api_successes"] == 1
    assert summary["contract_failures"] == 2


@pytest.mark.parametrize("value", ["{}", "[]", "not JSON", '{"foods": null}'])
def test_invalid_roots_fail(value):
    assert benchmark.check_response(value, EXPECTED)


@pytest.mark.parametrize("existing_override", [False, True])
@pytest.mark.parametrize("exception", [None, RuntimeError, asyncio.CancelledError])
def test_observer_restores_singleton_and_discards_private_responses(existing_override, exception):
    calls = []
    response_object = object()

    def create(**kwargs):
        calls.append(kwargs)
        return response_object

    original_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    class Provider:
        def _get_client(self):
            return original_client

    provider = Provider()
    if existing_override:
        provider._get_client = lambda: original_client
    before = provider.__dict__.copy()

    def scenario():
        with benchmark.observe_provider_responses(provider) as captured:
            assert provider._get_client().chat.completions.create(model="synthetic") is response_object
            assert captured == [response_object]
            if exception:
                raise exception()
        return captured

    if exception:
        with pytest.raises(exception):
            scenario()
    else:
        assert scenario() == []
    assert provider.__dict__ == before
    assert provider._get_client() is original_client
    assert calls == [{"model": "synthetic"}]


@pytest.mark.parametrize("food_count", [0, 1])
def test_explicit_provider_failure_cannot_pass_as_food_or_nonfood(food_count):
    value = response()
    value["success"] = False
    if not food_count:
        value["foods"] = []
    assert "explicit_recognition_failure" in benchmark.check_response(json.dumps(value), {"food_count": food_count})


@pytest.mark.parametrize("name", [None, 123, True, [], "", " \t\n"])
def test_missing_food_identity_cannot_pass_count_only_oracle(name):
    value = response()
    value["foods"][0]["name"] = name
    assert "invalid_food_name" in benchmark.check_response(json.dumps(value), {"food_count": 1})


def test_valid_food_identity_preserves_unknown_nutrition_and_confidence():
    value = response()
    for key in ["quantity_grams", "label_basis_grams", "calories", "protein", "carbs", "fat", "fiber", "confidence", "portion_confidence"]:
        value["foods"][0][key] = None
    assert benchmark.check_response(json.dumps(value), {"food_count": 1}) == []
