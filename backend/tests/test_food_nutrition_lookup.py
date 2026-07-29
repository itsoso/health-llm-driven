import pytest
from sqlalchemy import event

from app.models.food_nutrition import FoodItem, FoodNutrient
from app.services.food_nutrition_lookup import (
    calibrate_recognized_foods,
    enrich_food_from_table,
    quantity_as_grams,
)


def _add_chicken_breast(db):
    db.add(FoodItem(
        food_id="cfc:chicken_breast",
        canonical_name="鸡胸肉",
        aliases=["鸡肉", "鸡胸"],
        calibration_names=["鸡胸肉", "鸡胸"],
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
        "portion_basis": "vision_estimate",
        "portion_confidence": 0.73,
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
        "portion_basis": "vision_estimate",
        "portion_confidence": 0.73,
    }


def test_calibrate_recognized_foods_preserves_scaled_nutrition_label(db):
    _add_chicken_breast(db)
    foods = [{
        "name": "鸡胸肉",
        "quantity": "200g",
        "quantity_grams": 200,
        "calories": 412,
        "protein": 45,
        "carbs": 8,
        "fat": 22,
        "fiber": 1,
        "confidence": 0.96,
        "source": "nutrition_label",
        "nutrition_basis": "nutrition_label_scaled",
    }]

    calibrated = calibrate_recognized_foods(db, foods)

    assert calibrated[0] == foods[0]
    assert calibrated[0]["calories"] == 412
    assert calibrated[0]["protein"] == 45
    assert calibrated[0]["source"] == "nutrition_label"
    assert calibrated[0]["nutrition_basis"] == "nutrition_label_scaled"


def test_calibrate_recognized_foods_preserves_unscaled_nutrition_label(db):
    _add_chicken_breast(db)
    foods = [{
        "name": "鸡胸肉",
        "quantity": "每100g",
        "quantity_grams": 100,
        "label_basis_grams": 100,
        "calories": 206,
        "protein": 22.5,
        "carbs": 4,
        "fat": 11,
        "fiber": 0.5,
        "confidence": 0.96,
        "source": "nutrition_label",
        "nutrition_basis": "nutrition_label_per_100g",
    }]

    calibrated = calibrate_recognized_foods(db, foods)

    assert calibrated[0]["calories"] == 206
    assert calibrated[0]["protein"] == 22.5
    assert calibrated[0]["source"] == "nutrition_label"
    assert calibrated[0]["nutrition_basis"] == "nutrition_label_per_100g"


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


def test_calibrate_recognized_foods_keeps_ambiguous_alias_as_vision_estimate(db):
    _add_chicken_breast(db)

    calibrated = calibrate_recognized_foods(db, [{
        "name": "鸡肉",
        "quantity": "100g",
        "calories": 999,
    }])

    assert calibrated[0].get("food_id") is None
    assert calibrated[0]["calories"] == 999
    assert calibrated[0]["nutrition_basis"] == "vision_estimate"


def test_single_food_enrichment_also_rejects_ambiguous_alias(db):
    _add_chicken_breast(db)

    enriched = enrich_food_from_table(db, {
        "name": "鸡肉",
        "quantity": "100g",
        "calories": None,
    })

    assert enriched.get("food_id") is None
    assert enriched["calories"] is None


def test_calibrate_recognized_foods_matches_specific_reviewed_alias(db):
    _add_chicken_breast(db)

    calibrated = calibrate_recognized_foods(db, [{
        "name": "鸡胸",
        "quantity": "100g",
        "calories": 999,
    }])

    assert calibrated[0]["food_id"] == "cfc:chicken_breast"
    assert calibrated[0]["calories"] == 165.0
    assert calibrated[0]["nutrition_basis"] == "food_table"


def test_generic_canonical_name_is_not_calibrated_without_curator_opt_in(db):
    db.add(FoodItem(
        food_id="cfc:tofu_firm",
        canonical_name="豆腐",
        aliases=["北豆腐", "老豆腐"],
        calibration_names=["北豆腐", "老豆腐"],
        locale="zh-CN",
        source="china_food_composition",
    ))
    db.add(FoodNutrient(
        food_id="cfc:tofu_firm",
        kcal_per_100g=76.0,
        protein_g_per_100g=8.0,
        carbs_g_per_100g=1.9,
        fat_g_per_100g=4.8,
        fiber_g_per_100g=0.3,
        source="china_food_composition",
    ))
    db.commit()

    generic = calibrate_recognized_foods(db, [{
        "name": "豆腐", "quantity": "100g", "calories": 120,
    }])
    specific = calibrate_recognized_foods(db, [{
        "name": "北豆腐", "quantity": "100g", "calories": 120,
    }])

    assert generic[0].get("food_id") is None
    assert generic[0]["calories"] == 120
    assert generic[0]["nutrition_basis"] == "vision_estimate"
    assert specific[0]["food_id"] == "cfc:tofu_firm"
    assert specific[0]["calories"] == 76.0


def test_calibrate_recognized_foods_marks_partial_table_rows_as_mixed(db):
    _add_chicken_breast(db)
    nutrient = db.query(FoodNutrient).filter(
        FoodNutrient.food_id == "cfc:chicken_breast"
    ).one()
    nutrient.fiber_g_per_100g = None
    db.commit()

    calibrated = calibrate_recognized_foods(db, [{
        "name": "鸡胸肉",
        "quantity": "100g",
        "calories": 999,
        "protein": 1,
        "carbs": 50,
        "fat": 40,
        "fiber": 8,
    }])

    assert calibrated[0]["calories"] == 165.0
    assert calibrated[0]["fiber"] == 8
    assert calibrated[0]["source"] == "mixed"
    assert calibrated[0]["nutrition_basis"] == "mixed"


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
    assert "calibration_names" in statements[0]
