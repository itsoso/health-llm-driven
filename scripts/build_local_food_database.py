#!/usr/bin/env python3
"""Build the deterministic, offline USDA nutrition subset shipped by iOS.

The App never calls USDA at runtime. This builder accepts a reviewed source
snapshot, rejects unattributed rows, and emits a compact manifest + food table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "scripts" / "data" / "local_food_usda_sr_legacy_v1.json"
DEFAULT_OUTPUT = ROOT / "mobile" / "assets" / "food-nutrition"
NUTRIENTS = ("calories", "protein", "carbs", "fat", "fiber")


class BuildError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _positive_number(value: Any, *, allow_zero: bool = True) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value >= 0 if allow_zero else value > 0


def build(source: dict[str, Any]) -> dict[str, Any]:
    if source.get("schema_version") != 1:
        raise BuildError("unsupported source schema")
    if source.get("source") != "USDA FoodData Central":
        raise BuildError("unsupported source")
    if source.get("license") != "CC0-1.0":
        raise BuildError("source must be CC0-1.0")
    release = source.get("release")
    attribution = source.get("attribution")
    if not isinstance(release, str) or not release or not isinstance(attribution, str) or not attribution:
        raise BuildError("release and attribution are required")

    foods: list[dict[str, Any]] = []
    seen_food_ids: set[str] = set()
    seen_aliases: set[str] = set()
    for raw in source.get("foods", []):
        food_id = raw.get("food_id")
        fdc_id = raw.get("fdc_id")
        canonical_name = raw.get("canonical_name")
        if not isinstance(food_id, str) or not food_id or food_id.startswith("china_food_composition_manual_v1"):
            raise BuildError("invalid or forbidden food id")
        if food_id in seen_food_ids:
            raise BuildError("duplicate food id")
        seen_food_ids.add(food_id)
        if not isinstance(fdc_id, int) or isinstance(fdc_id, bool) or fdc_id <= 0:
            raise BuildError("every row requires an FDC id")
        if not isinstance(canonical_name, str) or not canonical_name.strip():
            raise BuildError("canonical name required")
        aliases = raw.get("aliases")
        if not isinstance(aliases, list) or not aliases:
            raise BuildError("aliases required")
        normalized_aliases = [str(alias).strip() for alias in aliases]
        all_names = [canonical_name.strip(), *normalized_aliases]
        if any(not alias for alias in all_names) or len(set(all_names)) != len(all_names):
            raise BuildError("duplicate or empty alias")
        for alias in all_names:
            if alias in seen_aliases:
                raise BuildError("alias collision")
            seen_aliases.add(alias)

        nutrients = raw.get("nutrients_per_100g")
        if not isinstance(nutrients, dict) or set(nutrients) != set(NUTRIENTS):
            raise BuildError("five required nutrients must be present")
        if any(not _positive_number(nutrients[name]) for name in NUTRIENTS):
            raise BuildError("nutrients must be finite non-negative numbers")

        portions: list[dict[str, Any]] = []
        for portion in raw.get("portions", []):
            unit = portion.get("unit")
            grams = portion.get("grams")
            basis = portion.get("basis")
            modifier = portion.get("source_modifier")
            if not isinstance(unit, str) or not unit or not _positive_number(grams, allow_zero=False):
                raise BuildError("invalid portion")
            if basis not in {"source_portion", "localized_estimate"}:
                raise BuildError("portion basis required")
            if not isinstance(modifier, str) or not modifier:
                raise BuildError("portion provenance required")
            portions.append({
                "unit": unit,
                "grams": grams,
                "basis": basis,
                "source_modifier": modifier,
            })

        foods.append({
            "food_id": food_id,
            "canonical_name": canonical_name.strip(),
            "aliases": sorted(normalized_aliases),
            "description": raw.get("description"),
            "nutrients_per_100g": {name: nutrients[name] for name in NUTRIENTS},
            "portions": sorted(portions, key=lambda item: item["unit"]),
            "source": {
                "provider": source["source"],
                "release": release,
                "fdc_id": fdc_id,
                "data_type": raw.get("data_type"),
            },
        })

    if not foods:
        raise BuildError("at least one food is required")
    foods.sort(key=lambda item: item["food_id"])
    foods_document = {"schema_version": 1, "foods": foods}
    digest = hashlib.sha256(_canonical_bytes(foods_document)).hexdigest()
    manifest = {
        "schema_version": 1,
        "database_version": "usda-sr-legacy-2018-04.zh-CN.v1",
        "source": source["source"],
        "release": release,
        "license": source["license"],
        "attribution": attribution,
        "transformation_version": "build_local_food_database.py.v1",
        "food_count": len(foods),
        "foods_sha256": digest,
    }
    return {"manifest": manifest, "foods": foods}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = json.loads(args.source.read_text())
    built = build(source)
    args.output.mkdir(parents=True, exist_ok=True)
    foods_document = {"schema_version": 1, "foods": built["foods"]}
    (args.output / "foods.json").write_bytes(_canonical_bytes(foods_document))
    (args.output / "manifest.json").write_bytes(_canonical_bytes(built["manifest"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
