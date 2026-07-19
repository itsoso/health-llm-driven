import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_local_food_database.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_local_food_database", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_source():
    return {
        "schema_version": 1,
        "source": "USDA FoodData Central",
        "release": "SR Legacy 2018-04",
        "license": "CC0-1.0",
        "attribution": "U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, 2019.",
        "foods": [
            {
                "food_id": "usda-1",
                "fdc_id": 1,
                "description": "Test food",
                "data_type": "SR Legacy",
                "canonical_name": "测试食物",
                "aliases": ["测试"],
                "nutrients_per_100g": {
                    "calories": 100,
                    "protein": 10,
                    "carbs": 20,
                    "fat": 2,
                    "fiber": 1,
                },
                "portions": [{
                    "unit": "个",
                    "grams": 50,
                    "basis": "source_portion",
                    "source_modifier": "large",
                }],
            }
        ],
    }


def test_build_is_deterministic_and_keeps_per_row_provenance():
    builder = load_builder()

    first = builder.build(valid_source())
    second = builder.build(valid_source())

    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )
    assert first["foods"][0]["source"] == {
        "provider": "USDA FoodData Central",
        "release": "SR Legacy 2018-04",
        "fdc_id": 1,
        "data_type": "SR Legacy",
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda source: source.update({"license": "unknown"}),
        lambda source: source["foods"][0].pop("fdc_id"),
        lambda source: source["foods"][0].update({"food_id": "china_food_composition_manual_v1"}),
        lambda source: source["foods"][0]["nutrients_per_100g"].update({"calories": -1}),
        lambda source: source["foods"][0].update({"aliases": ["测试", "测试"]}),
    ],
)
def test_build_rejects_unlicensed_unattributed_or_invalid_rows(mutate):
    builder = load_builder()
    source = valid_source()
    mutate(source)

    with pytest.raises(builder.BuildError):
        builder.build(source)
