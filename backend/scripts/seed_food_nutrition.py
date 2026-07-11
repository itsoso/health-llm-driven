#!/usr/bin/env python3
"""Seed reviewed food nutrition rows used by the diet voice parser."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SEED_FILE = ROOT / "data" / "food_nutrition_seed" / "china_common_foods.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-file", default=str(DEFAULT_SEED_FILE))
    args = parser.parse_args()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        counts = seed_food_nutrition(db, Path(args.seed_file))
        print(
            "seeded food nutrition: "
            f"{counts['food_items']} food_items, {counts['food_nutrients']} food_nutrients"
        )
        return 0
    finally:
        db.close()


def seed_food_nutrition(db, seed_file: Path = DEFAULT_SEED_FILE) -> dict[str, int]:
    from app.models.food_nutrition import FoodItem, FoodNutrient

    rows = _load_seed_rows(seed_file)
    item_count = 0
    nutrient_count = 0

    for row in rows:
        food_id = str(row["food_id"])
        item_payload = {
            "food_id": food_id,
            "canonical_name": row["canonical_name"],
            "aliases": row.get("aliases") or [],
            "calibration_names": row.get("calibration_names") or [],
            "locale": row.get("locale") or "zh-CN",
            "source": row["source"],
            "source_ref": row.get("source_ref"),
            "is_active": bool(row.get("is_active", True)),
        }
        existing_item = db.query(FoodItem).filter(FoodItem.food_id == food_id).first()
        if existing_item:
            for key, value in item_payload.items():
                setattr(existing_item, key, value)
        else:
            db.add(FoodItem(**item_payload))
        item_count += 1

        nutrients = row.get("nutrients") or {}
        nutrient_payload = {
            "food_id": food_id,
            "kcal_per_100g": nutrients.get("kcal_per_100g"),
            "protein_g_per_100g": nutrients.get("protein_g_per_100g"),
            "carbs_g_per_100g": nutrients.get("carbs_g_per_100g"),
            "fat_g_per_100g": nutrients.get("fat_g_per_100g"),
            "fiber_g_per_100g": nutrients.get("fiber_g_per_100g"),
            "source": row["source"],
            "source_ref": row.get("source_ref"),
        }
        existing_nutrient = db.query(FoodNutrient).filter(FoodNutrient.food_id == food_id).first()
        if existing_nutrient:
            for key, value in nutrient_payload.items():
                setattr(existing_nutrient, key, value)
        else:
            db.add(FoodNutrient(**nutrient_payload))
        nutrient_count += 1

    db.commit()
    return {"food_items": item_count, "food_nutrients": nutrient_count}


def _load_seed_rows(seed_file: Path) -> list[dict[str, Any]]:
    with seed_file.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise ValueError(f"food nutrition seed must be a list: {seed_file}")
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
