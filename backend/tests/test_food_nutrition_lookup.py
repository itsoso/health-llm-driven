import pytest
from sqlalchemy import event

from app.models.food_nutrition import FoodItem, FoodNutrient
from app.services.food_nutrition_lookup import (
    calibrate_recognized_foods,
    quantity_as_grams,
)


def _add_chicken_breast(db):
    db.add(FoodItem(
        food_id="cfc:chicken_breast",
        canonical_name="鸡胸肉",
        aliases=["鸡肉"],
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


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        ("200g", None, 200.0),
        ("200 克", None, 200.0),
        ("0.2kg", None, 200.0),
        ("半斤", None, 250.0),
        (200, "g", 200.0),
    ],
)
def test_quantity_as_grams_parses_explicit_chinese_portions(quantity, unit, expected):
    assert quantity_as_grams(quantity, unit) == expected


def test_calibrate_recognized_foods_uses_table_for_explicit_weight(db):
    _add_chicken_breast(db)
    foods = [{
        "name": "鸡胸肉",
        "quantity": "200g",
        "calories": 999,
        "protein": 1,
        "carbs": 50,
        "fat": 40,
        "fiber": 8,
        "confidence": 0.91,
    }]

    calibrated = calibrate_recognized_foods(db, foods)

    assert calibrated[0] == {
        "name": "鸡胸肉",
        "quantity": "200g",
        "quantity_grams": 200.0,
        "calories": 330.0,
        "protein": 62.0,
        "carbs": 0.0,
        "fat": 7.2,
        "fiber": 0.0,
        "confidence": 0.91,
        "food_id": "cfc:chicken_breast",
        "source": "china_food_composition",
        "nutrition_basis": "food_table",
    }


def test_calibrate_recognized_foods_keeps_model_estimate_without_weight(db):
    _add_chicken_breast(db)
    foods = [{
        "name": "鸡胸肉",
        "quantity": "1碗",
        "calories": 280,
        "protein": 45,
        "carbs": 2,
        "fat": 6,
        "confidence": 0.72,
    }]

    calibrated = calibrate_recognized_foods(db, foods)

    assert calibrated[0]["food_id"] == "cfc:chicken_breast"
    assert calibrated[0]["calories"] == 280
    assert calibrated[0]["protein"] == 45
    assert calibrated[0]["source"] == "ai_estimate"
    assert calibrated[0]["nutrition_basis"] == "vision_estimate"
    assert "quantity_grams" not in calibrated[0]


def test_calibrate_recognized_foods_matches_reviewed_alias(db):
    _add_chicken_breast(db)

    calibrated = calibrate_recognized_foods(db, [{
        "name": "鸡肉",
        "quantity": "100g",
        "calories": 999,
    }])

    assert calibrated[0]["food_id"] == "cfc:chicken_breast"
    assert calibrated[0]["calories"] == 165.0
    assert calibrated[0]["nutrition_basis"] == "food_table"


def test_batch_match_queries_only_requested_food_candidates(db):
    _add_chicken_breast(db)
    statements = []

    def capture_statement(_conn, _cursor, statement, _params, _context, _many):
        if "food_items" in statement and statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture_statement)
    try:
        calibrate_recognized_foods(db, [
            {"name": "鸡胸肉", "quantity": "100g"},
            {"name": "鸡肉", "quantity": "100g"},
        ])
    finally:
        event.remove(db.bind, "before_cursor_execute", capture_statement)

    assert len(statements) == 1
    assert "canonical_name IN" in statements[0]
    assert "aliases" in statements[0]
