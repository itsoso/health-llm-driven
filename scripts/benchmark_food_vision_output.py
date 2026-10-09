#!/usr/bin/env python3
"""Paired visual-output replay; private manifests/images never enter reports.

The default is dry-run. Live calls retain the production provider's destination
and per-dispatch consent guard, and never execute a diet write. Output contains
only metrics and predetermined contract failures, not pictures or model prose.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import re
import statistics
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

COMPACT_FORMAT = "输出格式：JSON 用单行紧凑格式，不加缩进或字段之间的空白；保留全部要求的字段与规则。"
FOOD_FIELDS = frozenset({
    "name", "quantity", "quantity_grams", "label_basis_grams", "calories",
    "protein", "carbs", "fat", "fiber", "confidence", "portion_confidence",
    "source", "nutrition_basis",
})


def check_response(content: str, expected: dict) -> list[str]:
    """Frozen contracts, not clinical truth or a general non-inferiority score."""
    try:
        value = json.loads(content)
    except (ValueError, TypeError):
        return ["invalid_json"]
    if not isinstance(value, dict) or not isinstance(value.get("foods"), list):
        return ["invalid_root"]
    foods = value["foods"]
    failures = []
    if value.get("success") is False:
        failures.append("explicit_recognition_failure")
    if not {"foods", "meal_description", "health_tips"} <= value.keys():
        failures.append("missing_top_fields")
    if len(foods) != expected["food_count"]:
        failures.append("wrong_food_count")
    for food in foods:
        if not isinstance(food, dict) or not FOOD_FIELDS <= food.keys():
            failures.append("missing_food_fields")
            continue
        if not isinstance(food["name"], str) or not food["name"].strip():
            failures.append("invalid_food_name")
        for key in ("quantity_grams", "label_basis_grams", "calories", "protein", "carbs", "fat", "fiber", "confidence", "portion_confidence"):
            number = food[key]
            if number is not None and (
                isinstance(number, bool) or not isinstance(number, (int, float))
                or not math.isfinite(number) or number < 0
            ):
                failures.append("invalid_numeric_field")
        for key in ("confidence", "portion_confidence"):
            if isinstance(food[key], (float, int)) and food[key] > 1:
                failures.append("invalid_probability")
    names = [str(food.get("name", "")) for food in foods if isinstance(food, dict)]
    for pattern in expected.get("food_name_patterns", []):
        if not any(re.search(pattern, name) for name in names):
            failures.append("missing_expected_food")
    for constraint in expected.get("exact_food_values", []):
        index = constraint["index"]
        if index >= len(foods) or not isinstance(foods[index], dict):
            failures.append("missing_constrained_food")
            continue
        for key, wanted in constraint["values"].items():
            actual = foods[index].get(key, object())
            if isinstance(wanted, (float, int)) and not isinstance(wanted, bool):
                equal = not isinstance(actual, bool) and isinstance(actual, (float, int)) and math.isfinite(actual) and abs(actual - wanted) <= constraint.get("tolerance", 0)
            else:
                equal = actual == wanted
            if not equal:
                failures.append("wrong_constrained_value")
    if any(re.search(r"已(?:保存|记录|食用)", str(value.get(key, ""))) for key in ("meal_description", "health_tips")):
        failures.append("unauthorized_completion_claim")
    return sorted(set(failures))


def summarize(rows: list[dict]) -> dict:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["variant"]].append(row)
    summary = {}
    for variant, group in grouped.items():
        successful = [r for r in group if r["api_success"]]
        times = sorted(r["latency_ms"] for r in successful)
        def quantile(p, values=times):
            if not values:
                return None
            position = (len(values) - 1) * p
            lo = int(position)
            return round(values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (position - lo))
        summary[variant] = {
            "attempts": len(group), "api_successes": len(successful),
            "contract_failures": sum(bool(r["failures"]) for r in group),
            "p50_ms": quantile(.5), "sample_p95_ms": quantile(.95),
            "sample_p99_ms": quantile(.99),
            "mean_output_tokens": round(statistics.mean(r["completion_tokens"] for r in successful if r["completion_tokens"] is not None), 2) if any(r.get("completion_tokens") is not None for r in successful) else None,
        }
    return summary


@contextmanager
def observe_provider_responses(provider):
    """Restore the singleton's exact state even after failure or cancellation."""
    missing = object()
    previous = provider.__dict__.get("_get_client", missing)
    original_client = provider._get_client()
    captured = []

    def create(**kwargs):
        response = original_client.chat.completions.create(**kwargs)
        captured.append(response)
        return response

    observer = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider._get_client = lambda: observer
    try:
        yield captured
    finally:
        captured.clear()
        if previous is missing:
            del provider._get_client
        else:
            provider._get_client = previous


def variant_prompt(variant):
    from app.services.ai.food_recognition import (
        FOOD_RECOGNITION_SYSTEM_PROMPT,
        _food_recognition_request_prompt,
    )
    if variant == "wire":
        return _food_recognition_request_prompt()
    return FOOD_RECOGNITION_SYSTEM_PROMPT + ("\n" + COMPACT_FORMAT if variant == "compact" else "")


def normalize_replay_response(content, variant):
    from app.services.ai.food_recognition import (
        _expand_food_recognition_wire_payload,
        extract_json_from_text,
    )
    extracted = extract_json_from_text(content)
    if variant == "wire":
        return json.dumps(_expand_food_recognition_wire_payload(json.loads(extracted)), ensure_ascii=False)
    return extracted


async def replay(cases, variants, repeats, user_id):
    from app.services.ai.food_recognition import (
        _vision_chat_options,
    )
    from app.services.ai_consent import ai_user_scope
    from app.services.llm.factory import get_vision_provider

    provider = get_vision_provider()
    rows = []
    # The observer forwards to the original guarded SDK client.
    with observe_provider_responses(provider) as captured, ai_user_scope(user_id):
        for repeat in range(repeats):
            for case_index, case in enumerate(cases):
                image = Path(case["image_path"]).read_bytes()
                encoded = base64.b64encode(image).decode("ascii")
                order = variants if (repeat + case_index) % 2 == 0 else variants[::-1]
                for variant in order:
                    captured.clear()
                    start = time.perf_counter()
                    row = {"sample": f"sample-{case_index + 1}", "repeat": repeat, "variant": variant, "api_success": False, "failures": []}
                    try:
                        prompt = variant_prompt(variant)
                        model = provider.model
                        if variant == "flash":
                            model = "qwen3-vl-flash"
                        content = await provider.chat_with_vision(
                            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": "请识别这张图片中的食物，并估算营养信息。"}],
                            image_url=f"data:image/{case.get('image_type', 'jpeg')};base64,{encoded}",
                            model=model, temperature=0.1, max_tokens=2000,
                            **_vision_chat_options(SimpleNamespace(model=model)),
                        )
                        response = captured[-1]
                        usage = response.usage
                        row.update(api_success=True, model=model, response_chars=len(content), prompt_tokens=getattr(usage, "prompt_tokens", None), completion_tokens=getattr(usage, "completion_tokens", None), cached_tokens=getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", None), failures=check_response(normalize_replay_response(content, variant), case["expected"]))
                        if response.choices[0].finish_reason != "stop":
                            row["failures"].append("incomplete_response")
                    except Exception as exc:  # noqa: BLE001 -- retain failures without logging private API response bodies
                        row.update(error_type=type(exc).__name__, failures=["api_or_evaluation_failure"])
                    row["latency_ms"] = round((time.perf_counter() - start) * 1000)
                    rows.append(row)
                    print(json.dumps(row), flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--include-live-llm", action="store_true")
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--variants", nargs="+", choices=("baseline", "compact", "wire", "flash"), default=["baseline", "compact"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.manifest.read_text())
    if not isinstance(cases, list) or not cases or not 1 <= args.repeats <= 5 or len(cases) > 12 or len(set(args.variants)) != len(args.variants) or not {"baseline", "compact"}.intersection(args.variants):
        parser.error("require 1-12 cases, 1-5 repeats and distinct variants including baseline or compact")
    if args.include_live_llm and (args.user_id is None or args.user_id <= 0):
        parser.error("live replay requires an existing consented --user-id")
    # Validate frozen oracles before any billable request.
    for case in cases:
        if not isinstance(case, dict) or not Path(case["image_path"]).is_file() or type(case["expected"]["food_count"]) is not int or not 0 <= case["expected"]["food_count"] <= 12:
            parser.error("invalid case or missing image")
    rows = asyncio.run(replay(cases, args.variants, args.repeats, args.user_id)) if args.include_live_llm else []
    report = {"kind": "food_vision_output_replay", "live": args.include_live_llm, "sample_count": len(cases), "repeats": args.repeats, "rows": rows, "summary": summarize(rows), "unknowns": ["clinical nutrition truth for photographs", "general semantic non-inferiority", "production end-to-end P95", "actual diet persistence"]}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    return int(any(row["failures"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
