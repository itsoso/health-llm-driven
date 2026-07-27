"""Deterministic food nutrition lookup for diet draft enrichment."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.food_nutrition import FoodItem, FoodNutrient

logger = logging.getLogger(__name__)

_NUTRIENT_FIELDS = (
    ("calories", "kcal_per_100g"),
    ("protein", "protein_g_per_100g"),
    ("carbs", "carbs_g_per_100g"),
    ("fat", "fat_g_per_100g"),
    ("fiber", "fiber_g_per_100g"),
)
_NUTRITION_LABEL_BASES = {
    "nutrition_label",
    "nutrition_label_scaled",
    "nutrition_label_per_100g",
    "nutrition_label_per_serving",
}

@dataclass(frozen=True)
class FoodNutritionMatch:
    food_id: str
    source: str
    nutrient: FoodNutrient


def enrich_foods_from_table(db: Session, foods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach food_id/source and fill missing nutrients from reviewed food tables."""
    matches = find_food_matches(db, [food.get("name") for food in foods])
    for food in foods:
        name_key = normalize_food_key(food.get("name"))
        match = matches.get(name_key)
        if match is not None:
            _enrich_food_with_match(food, match)
    return foods


def enrich_food_from_table(db: Session, food: dict[str, Any]) -> dict[str, Any]:
    name = str(food.get("name") or "").strip()
    if not name:
        return food

    match = find_food_match(db, name)
    if match is None:
        return food

    return _enrich_food_with_match(food, match)


def calibrate_recognized_foods(
    db: Session,
    foods: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Calibrate photo-recognition nutrients when a reviewed, weighted match exists.

    Vision estimates remain visible when a portion cannot be converted to grams.
    This avoids presenting a table source for nutrients that were not table-derived.
    """
    matches = find_food_matches(db, [food.get("name") for food in foods])
    for food in foods:
        if _has_nutrition_label_values(food):
            food.setdefault("source", "nutrition_label")
            continue

        match = matches.get(normalize_food_key(food.get("name")))
        if match is None:
            food.setdefault("source", "ai_estimate")
            food["nutrition_basis"] = "vision_estimate"
            continue

        food["food_id"] = match.food_id
        grams = quantity_as_grams(food.get("quantity"), food.get("unit"))
        if grams is None:
            food["source"] = "ai_estimate"
            food["nutrition_basis"] = "vision_estimate"
            food.pop("quantity_grams", None)
            continue

        food["quantity_grams"] = round(grams, 1)
        table_values = {
            output_key: _scale_nutrient(getattr(match.nutrient, nutrient_key), grams)
            for output_key, nutrient_key in _NUTRIENT_FIELDS
        }
        available_count = sum(value is not None for value in table_values.values())
        if available_count == 0:
            food["source"] = "ai_estimate"
            food["nutrition_basis"] = "vision_estimate"
            continue
        fully_calibrated = available_count == len(_NUTRIENT_FIELDS)
        food["source"] = match.source if fully_calibrated else "mixed"
        food["nutrition_basis"] = "food_table" if fully_calibrated else "mixed"
        for output_key, nutrient_key in _NUTRIENT_FIELDS:
            table_value = table_values[output_key]
            _log_divergence(food, output_key, table_value)
            if table_value is not None:
                food[output_key] = table_value

    return foods


def _has_nutrition_label_values(food: dict[str, Any]) -> bool:
    basis = str(food.get("nutrition_basis") or "").strip().lower()
    if basis not in _NUTRITION_LABEL_BASES:
        return False
    calories = _to_float(food.get("calories"))
    macros = (
        _to_float(food.get("protein")),
        _to_float(food.get("carbs")),
        _to_float(food.get("fat")),
    )
    return bool(
        calories is not None
        and calories > 0
        and any(value is not None and value > 0 for value in macros)
    )


def _enrich_food_with_match(
    food: dict[str, Any],
    match: FoodNutritionMatch,
) -> dict[str, Any]:

    food["food_id"] = match.food_id
    food["source"] = match.source

    grams = quantity_as_grams(food.get("quantity"), food.get("unit"))
    if grams is None:
        return food

    for output_key, nutrient_key in _NUTRIENT_FIELDS:
        per_100g = getattr(match.nutrient, nutrient_key)
        table_value = _scale_nutrient(per_100g, grams)
        _log_divergence(food, output_key, table_value)
        if food.get(output_key) is None and table_value is not None:
            food[output_key] = table_value

    return food


def find_food_matches(db: Session, names: list[Any]) -> dict[str, FoodNutritionMatch]:
    """Resolve only curator-approved calibration identities without N+1 queries."""
    raw_names = sorted({str(name or "").strip() for name in names if str(name or "").strip()})
    requested = {normalize_food_key(name) for name in raw_names}
    requested.discard("")
    if not requested:
        return {}

    if db.get_bind().dialect.name == "sqlite":
        calibration_values = (
            func.json_each(FoodItem.calibration_names)
            .table_valued("key", "value")
            .alias("food_calibration_name")
        )
        candidate_filter = exists(
            select(1)
            .select_from(calibration_values)
            .where(calibration_values.c.value.in_(raw_names))
        )
    else:
        candidate_filter = or_(
            *(FoodItem.calibration_names.contains([name]) for name in raw_names)
        )
    rows = (
        db.query(FoodItem, FoodNutrient)
        .join(FoodNutrient, FoodNutrient.food_id == FoodItem.food_id)
        .filter(FoodItem.is_active.is_(True), candidate_filter)
        .order_by(FoodItem.food_id.asc())
        .all()
    )
    candidates: dict[str, list[FoodNutritionMatch]] = {}
    for item, nutrient in rows:
        calibration_names = (
            item.calibration_names
            if isinstance(item.calibration_names, list)
            else []
        )
        for key in requested.intersection({normalize_food_key(name) for name in calibration_names}):
            candidates.setdefault(key, []).append(_to_match(item, nutrient))
    return {
        key: values[0]
        for key, values in candidates.items()
        if len({value.food_id for value in values}) == 1
    }


def find_food_match(db: Session, name: str) -> FoodNutritionMatch | None:
    key = normalize_food_key(name)
    if not key:
        return None
    return find_food_matches(db, [name]).get(key)


def normalize_food_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", "", text)


def _to_match(item: FoodItem, nutrient: FoodNutrient) -> FoodNutritionMatch:
    return FoodNutritionMatch(
        food_id=item.food_id,
        source=nutrient.source or item.source,
        nutrient=nutrient,
    )


def quantity_as_grams(quantity: Any, unit: Any = None) -> float | None:
    """Parse only explicit mass units; bowls, servings and pieces stay estimates."""
    quantity_text = str(quantity or "").strip().lower()
    compact = re.sub(r"\s+", "", quantity_text)

    half_match = re.search(r"半(公斤|千克|kg|kilogram|kilograms|斤)", compact)
    if half_match:
        return 500.0 if half_match.group(1) != "斤" else 250.0

    embedded = re.search(
        r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>kilograms?|kg|公斤|千克|grams?|g|克|斤)",
        quantity_text,
    )
    if embedded:
        return _mass_to_grams(float(embedded.group("amount")), embedded.group("unit"))

    amount = _to_float(quantity)
    if amount is None or amount <= 0:
        return None
    return _mass_to_grams(amount, str(unit or "").strip().lower())


def _mass_to_grams(amount: float, unit: str) -> float | None:
    if amount <= 0:
        return None
    if unit in {"g", "gram", "grams", "克"}:
        return amount
    if unit in {"kg", "kilogram", "kilograms", "公斤", "千克"}:
        return amount * 1000
    if unit == "斤":
        return amount * 500
    return None


def _scale_nutrient(per_100g: Any, grams: float) -> float | None:
    value = _to_float(per_100g)
    if value is None:
        return None
    return round(value * grams / 100.0, 1)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _log_divergence(food: dict[str, Any], key: str, table_value: float | None) -> None:
    current = _to_float(food.get(key))
    if current is None or table_value is None:
        return
    baseline = max(abs(table_value), 1.0)
    if abs(current - table_value) / baseline >= 0.25:
        logger.debug(
            "[diet_voice] table nutrition differs from draft estimate: food_id=%s nutrient=%s",
            food.get("food_id"),
            key,
        )
