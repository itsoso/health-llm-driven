"""Deterministic food nutrition lookup for diet draft enrichment."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class FoodNutritionMatch:
    food_id: str
    source: str
    nutrient: FoodNutrient


def enrich_foods_from_table(db: Session, foods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach food_id/source and fill missing nutrients from reviewed food tables."""
    for food in foods:
        enrich_food_from_table(db, food)
    return foods


def enrich_food_from_table(db: Session, food: dict[str, Any]) -> dict[str, Any]:
    name = str(food.get("name") or "").strip()
    if not name:
        return food

    match = find_food_match(db, name)
    if match is None:
        return food

    food["food_id"] = match.food_id
    food["source"] = match.source

    grams = _quantity_as_grams(food.get("quantity"), food.get("unit"))
    if grams is None:
        return food

    for output_key, nutrient_key in _NUTRIENT_FIELDS:
        per_100g = getattr(match.nutrient, nutrient_key)
        table_value = _scale_nutrient(per_100g, grams)
        _log_divergence(food, output_key, table_value)
        if food.get(output_key) is None and table_value is not None:
            food[output_key] = table_value

    return food


def find_food_match(db: Session, name: str) -> FoodNutritionMatch | None:
    key = normalize_food_key(name)
    if not key:
        return None

    exact = (
        db.query(FoodItem, FoodNutrient)
        .join(FoodNutrient, FoodNutrient.food_id == FoodItem.food_id)
        .filter(FoodItem.is_active.is_(True), FoodItem.canonical_name == name)
        .first()
    )
    if exact is not None:
        return _to_match(*exact)

    rows = (
        db.query(FoodItem, FoodNutrient)
        .join(FoodNutrient, FoodNutrient.food_id == FoodItem.food_id)
        .filter(FoodItem.is_active.is_(True))
        .limit(1000)
        .all()
    )
    for item, nutrient in rows:
        terms = [item.canonical_name, *((item.aliases or []) if isinstance(item.aliases, list) else [])]
        if key in {normalize_food_key(term) for term in terms}:
            return _to_match(item, nutrient)
    return None


def normalize_food_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", "", text)


def _to_match(item: FoodItem, nutrient: FoodNutrient) -> FoodNutritionMatch:
    return FoodNutritionMatch(
        food_id=item.food_id,
        source=nutrient.source or item.source,
        nutrient=nutrient,
    )


def _quantity_as_grams(quantity: Any, unit: Any) -> float | None:
    amount = _to_float(quantity)
    if amount is None or amount <= 0:
        return None

    unit_text = str(unit or "").strip().lower()
    if unit_text in {"g", "gram", "grams", "克"}:
        return amount
    if unit_text in {"kg", "kilogram", "kilograms", "公斤", "千克"}:
        return amount * 1000
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
