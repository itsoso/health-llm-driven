from app.models.food_nutrition import FoodItem, FoodNutrient
from scripts.seed_food_nutrition import seed_food_nutrition


def test_food_nutrition_seed_is_idempotent_and_keeps_calibration_specific(db):
    first = seed_food_nutrition(db)
    second = seed_food_nutrition(db)

    assert first == {"food_items": 6, "food_nutrients": 6}
    assert second == first
    assert db.query(FoodItem).count() == 6
    assert db.query(FoodNutrient).count() == 6

    chicken = db.query(FoodItem).filter_by(food_id="cfc:chicken_breast").one()
    tofu = db.query(FoodItem).filter_by(food_id="cfc:tofu_firm").one()

    assert "鸡肉" in chicken.aliases
    assert "鸡肉" not in chicken.calibration_names
    assert tofu.canonical_name == "豆腐"
    assert tofu.calibration_names == ["北豆腐", "老豆腐"]
