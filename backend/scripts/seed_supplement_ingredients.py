#!/usr/bin/env python3
"""Seed reviewed supplement ingredient rows used by supplement guardrails."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SEED_FILE = ROOT / "data" / "supplement_ingredient_seed" / "reviewed_uls.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-file", default=str(DEFAULT_SEED_FILE))
    args = parser.parse_args()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        counts = seed_supplement_ingredients(db, Path(args.seed_file))
        print(f"seeded supplement ingredients: {counts['supplement_ingredients']} rows")
        return 0
    finally:
        db.close()


def seed_supplement_ingredients(db, seed_file: Path = DEFAULT_SEED_FILE) -> dict[str, int]:
    from app.models.supplement_ingredient import SupplementIngredient

    rows = _load_seed_rows(seed_file)
    count = 0

    for row in rows:
        ingredient_id = str(row["ingredient_id"])
        payload = {
            "ingredient_id": ingredient_id,
            "canonical_name": row["canonical_name"],
            "aliases": row.get("aliases") or [],
            "ul_amount": row.get("ul_amount"),
            "ul_unit": row.get("ul_unit"),
            "source": row["source"],
            "source_ref": row.get("source_ref"),
            "is_active": bool(row.get("is_active", True)),
        }
        existing = (
            db.query(SupplementIngredient)
            .filter(SupplementIngredient.ingredient_id == ingredient_id)
            .first()
        )
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
        else:
            db.add(SupplementIngredient(**payload))
        count += 1

    db.commit()
    return {"supplement_ingredients": count}


def _load_seed_rows(seed_file: Path) -> list[dict[str, Any]]:
    with seed_file.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise ValueError(f"supplement ingredient seed must be a list: {seed_file}")
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
