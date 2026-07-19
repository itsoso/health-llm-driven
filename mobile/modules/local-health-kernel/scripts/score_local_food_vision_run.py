#!/usr/bin/env python3
"""Score and calibrate non-private Chinese-CLIP identity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable


MINIMUM_DATASET_CASES = 300
MAXIMUM_ASSET_BYTES = 50 * 1024 * 1024
MINIMUM_SCORE_FLOOR = 0.5
MINIMUM_MARGIN_FLOOR = 0.03
MAXIMUM_CANDIDATES = 3
ALLOWED_LICENSES = {"licensed_for_evaluation", "public_domain", "synthetic"}
REQUIRED_STRATA = {
    "single_item",
    "composite_dish",
    "mixed_plate",
    "packaged_food_drink",
    "confusable_pair",
    "non_food_adversarial",
    "degraded_adversarial",
}
OPAQUE_ID = re.compile(r"^(?:case|fixture)-[a-z0-9][a-z0-9_-]*$")
QUALITY_THRESHOLDS = {
    "crashFreeCompletionRate": ("minimum", 1.0),
    "validTypedDraftRate": ("minimum", 0.95),
    "foodIdentityPrecision": ("minimum", 0.85),
    "missingItemRate": ("maximum", 0.1),
    "nonFoodRejectionRate": ("minimum", 0.98),
    "medianCorrectionCount": ("maximum", 1.0),
    "p90CorrectionCount": ("maximum", 2.0),
}


class ScoringError(ValueError):
    """Raised when evidence is incomplete, private, ambiguous or malformed."""


def _require_keys(value: dict[str, Any], required: set[str], field: str) -> None:
    missing = required - set(value)
    if missing:
        raise ScoringError(f"{field} is missing keys: {sorted(missing)}")


def _require_exact_keys(value: dict[str, Any], expected: set[str], field: str) -> None:
    _require_keys(value, expected, field)
    extra = set(value) - expected
    if extra:
        raise ScoringError(f"{field} has forbidden keys: {sorted(extra)}")


def validate_dataset_manifest(
    manifest: dict[str, Any], minimum_cases: int = MINIMUM_DATASET_CASES
) -> None:
    _require_exact_keys(
        manifest,
        {"schemaVersion", "datasetVersion", "containsPrivateUserData", "cases"},
        "dataset manifest",
    )
    if manifest["schemaVersion"] != 1:
        raise ScoringError("dataset schemaVersion must equal 1")
    if manifest["containsPrivateUserData"] is not False:
        raise ScoringError("private user data is forbidden")
    if not isinstance(manifest["datasetVersion"], str) or not manifest["datasetVersion"]:
        raise ScoringError("datasetVersion must be non-empty")
    cases = manifest["cases"]
    if not isinstance(cases, list) or len(cases) < minimum_cases:
        raise ScoringError(f"dataset requires at least {minimum_cases} cases")

    case_ids: set[str] = set()
    fixture_ids: set[str] = set()
    strata: set[str] = set()
    splits: set[str] = set()
    required_case_keys = {
        "caseId",
        "fixtureId",
        "split",
        "stratum",
        "licenseStatus",
        "expectedFoodIdentities",
        "nonFood",
    }
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ScoringError(f"cases[{index}] must be an object")
        _require_exact_keys(case, required_case_keys, f"cases[{index}]")
        case_id = case["caseId"]
        fixture_id = case["fixtureId"]
        if not isinstance(case_id, str) or not OPAQUE_ID.fullmatch(case_id):
            raise ScoringError(f"cases[{index}].caseId must be opaque")
        if not isinstance(fixture_id, str) or not OPAQUE_ID.fullmatch(fixture_id):
            raise ScoringError(f"cases[{index}].fixtureId must be opaque")
        if case_id in case_ids or fixture_id in fixture_ids:
            raise ScoringError("caseId and fixtureId must be unique")
        case_ids.add(case_id)
        fixture_ids.add(fixture_id)

        split = case["split"]
        stratum = case["stratum"]
        if split not in {"calibration", "test"}:
            raise ScoringError(f"cases[{index}].split is invalid")
        if stratum not in REQUIRED_STRATA:
            raise ScoringError(f"cases[{index}].stratum is invalid")
        if case["licenseStatus"] not in ALLOWED_LICENSES:
            raise ScoringError(f"cases[{index}] has unclear license")
        splits.add(split)
        strata.add(stratum)

        expected = case["expectedFoodIdentities"]
        if not isinstance(expected, list) or any(
            not isinstance(item, str) or not item for item in expected
        ) or len(expected) != len(set(expected)):
            raise ScoringError(f"cases[{index}].expectedFoodIdentities is invalid")
        if not isinstance(case["nonFood"], bool):
            raise ScoringError(f"cases[{index}].nonFood must be boolean")
        if case["nonFood"] and expected:
            raise ScoringError("non-food cases cannot have expected food identities")
        if stratum == "mixed_plate" and len(expected) < 2:
            raise ScoringError("mixed_plate cases require at least two identities")

    if not REQUIRED_STRATA.issubset(strata):
        raise ScoringError(f"dataset is missing strata: {sorted(REQUIRED_STRATA - strata)}")
    if splits != {"calibration", "test"}:
        raise ScoringError("dataset requires independent calibration and test splits")


def _percentile(values: Iterable[float], probability: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[min(index, len(ordered) - 1)]


def _metrics(cases: list[dict[str, Any]], include_strata: bool) -> dict[str, Any]:
    if not cases:
        raise ScoringError("at least one scored case is required")
    true_positives = 0
    predicted_count = 0
    missing_count = 0
    expected_count = 0
    corrections: list[int] = []
    food_cases = 0
    top1_hits = 0
    top3_hits = 0
    non_food_count = 0
    non_food_rejections = 0
    crash_free = 0
    valid_drafts = 0
    one_second = 0
    warm_latencies: list[float] = []

    for index, case in enumerate(cases):
        _require_keys(
            case,
            {
                "expectedFoodIdentities",
                "predictedFoodIdentities",
                "nonFood",
                "crashed",
                "validTypedDraft",
                "warmLatencyMs",
                "stratum",
            },
            f"result case {index}",
        )
        expected = set(case["expectedFoodIdentities"])
        predicted_ordered = list(dict.fromkeys(case["predictedFoodIdentities"]))
        predicted = set(predicted_ordered)
        true_positives += len(expected & predicted)
        predicted_count += len(predicted)
        missing_count += len(expected - predicted)
        expected_count += len(expected)
        corrections.append(len(expected.symmetric_difference(predicted)))

        if expected:
            food_cases += 1
            top1_hits += int(bool(expected & set(predicted_ordered[:1])))
            top3_hits += int(bool(expected & set(predicted_ordered[:3])))
        if case["nonFood"]:
            non_food_count += 1
            non_food_rejections += int(not predicted and not case["crashed"])
        if not case["crashed"]:
            crash_free += 1
            warm = float(case["warmLatencyMs"])
            if not math.isfinite(warm) or warm < 0:
                raise ScoringError("warm latency must be finite and non-negative")
            warm_latencies.append(warm)
            one_second += int(warm <= 1_000)
        valid_drafts += int(bool(case["validTypedDraft"]) and not case["crashed"])

    count = len(cases)
    result: dict[str, Any] = {
        "caseCount": count,
        "crashFreeCompletionRate": crash_free / count,
        "validTypedDraftRate": valid_drafts / count,
        "foodIdentityPrecision": (
            true_positives / predicted_count if predicted_count else 1.0
        ),
        "missingItemRate": missing_count / expected_count if expected_count else 0.0,
        "nonFoodRejectionRate": (
            non_food_rejections / non_food_count if non_food_count else 1.0
        ),
        "medianCorrectionCount": _percentile(corrections, 0.5) or 0.0,
        "p90CorrectionCount": _percentile(corrections, 0.9) or 0.0,
        "top1Accuracy": top1_hits / food_cases if food_cases else 1.0,
        "top3Accuracy": top3_hits / food_cases if food_cases else 1.0,
        "p95WarmLatencyMs": _percentile(warm_latencies, 0.95),
        "oneSecondCompletionRate": one_second / count,
    }
    if include_strata:
        result["perStratum"] = {
            stratum: _metrics(
                [case for case in cases if case["stratum"] == stratum],
                include_strata=False,
            )
            for stratum in sorted({case["stratum"] for case in cases})
        }
    return result


def compute_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return _metrics(cases, include_strata=True)


def quality_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for field, (direction, threshold) in QUALITY_THRESHOLDS.items():
        value = metrics.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            failures.append(field)
        elif direction == "minimum" and value < threshold:
            failures.append(field)
        elif direction == "maximum" and value > threshold:
            failures.append(field)
    per_stratum = metrics.get("perStratum")
    if isinstance(per_stratum, dict):
        for stratum, stratum_metrics in sorted(per_stratum.items()):
            stratum_gate = quality_gate(stratum_metrics)
            failures.extend(
                f"perStratum.{stratum}.{field}"
                for field in stratum_gate["failures"]
            )
    return {"passed": not failures, "failures": failures}


def compare_variants(
    fp16_metrics: dict[str, Any],
    compressed_metrics: dict[str, Any],
    *,
    fp16_asset_bytes: int,
    compressed_asset_bytes: int,
) -> dict[str, Any]:
    delta = abs(
        float(fp16_metrics["foodIdentityPrecision"])
        - float(compressed_metrics["foodIdentityPrecision"])
    )
    fp16_gate = quality_gate(fp16_metrics)
    compressed_gate = quality_gate(compressed_metrics)
    compressed_passes = (
        compressed_gate["passed"]
        and delta <= 0.02
        and compressed_asset_bytes <= MAXIMUM_ASSET_BYTES
    )
    fp16_passes = fp16_gate["passed"] and fp16_asset_bytes <= MAXIMUM_ASSET_BYTES
    selected = "compressed" if compressed_passes else ("fp16" if fp16_passes else None)
    return {
        "verdict": "pass" if selected else "blocked",
        "selectedVariant": selected,
        "absoluteIdentityPrecisionDelta": delta,
        "fp16QualityGate": fp16_gate,
        "compressedQualityGate": compressed_gate,
        "fp16AssetBytes": fp16_asset_bytes,
        "compressedAssetBytes": compressed_asset_bytes,
        "assetBudgetBytes": MAXIMUM_ASSET_BYTES,
    }


def _prediction_for_policy(
    candidate_row: dict[str, Any], minimum_score: float, minimum_margin: float
) -> list[str]:
    candidates = sorted(
        candidate_row.get("candidates", []),
        key=lambda item: (-float(item["score"]), item["canonicalFoodId"]),
    )
    if not candidates or float(candidates[0]["score"]) < minimum_score:
        return []
    if candidates[0]["kind"] == "non_food":
        return []
    foods = [item for item in candidates if item["kind"] == "food"]
    if not foods or float(foods[0]["score"]) < minimum_score:
        return []
    if len(foods) > 1 and float(foods[0]["score"]) - float(foods[1]["score"]) < minimum_margin:
        return []
    return [
        item["canonicalFoodId"]
        for item in foods
        if float(item["score"]) >= minimum_score
    ][:MAXIMUM_CANDIDATES]


def _split_hash(case_ids: list[str]) -> str:
    value = "".join(f"{case_id}\n" for case_id in sorted(case_ids)).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def calibrate_thresholds(
    manifest: dict[str, Any], candidate_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    validate_dataset_manifest(manifest, minimum_cases=1)
    metadata = {case["caseId"]: case for case in manifest["cases"]}
    rows = {row["caseId"]: row for row in candidate_rows}
    missing = set(metadata) - set(rows)
    if missing:
        raise ScoringError(f"candidate evidence is missing cases: {sorted(missing)}")
    calibration_ids = [
        case_id for case_id, case in metadata.items() if case["split"] == "calibration"
    ]
    test_ids = [case_id for case_id, case in metadata.items() if case["split"] == "test"]

    score_values = {MINIMUM_SCORE_FLOOR}
    margin_values = {MINIMUM_MARGIN_FLOOR}
    for case_id in calibration_ids:
        candidates = sorted(
            rows[case_id].get("candidates", []),
            key=lambda item: -float(item["score"]),
        )
        score_values.update(
            float(item["score"])
            for item in candidates
            if float(item["score"]) >= MINIMUM_SCORE_FLOOR
        )
        foods = [item for item in candidates if item["kind"] == "food"]
        if len(foods) > 1:
            margin = float(foods[0]["score"]) - float(foods[1]["score"])
            if margin >= MINIMUM_MARGIN_FLOOR:
                margin_values.add(margin)

    viable: list[tuple[int, float, float, dict[str, Any]]] = []
    for minimum_score in sorted(score_values):
        for minimum_margin in sorted(margin_values):
            scored_cases = []
            coverage = 0
            for case_id in calibration_ids:
                case = metadata[case_id]
                predicted = _prediction_for_policy(
                    rows[case_id], minimum_score, minimum_margin
                )
                coverage += int(bool(predicted) or case["nonFood"])
                scored_cases.append(
                    {
                        **case,
                        "predictedFoodIdentities": predicted,
                        "crashed": False,
                        "validTypedDraft": bool(predicted) or case["nonFood"],
                        "warmLatencyMs": 0,
                    }
                )
            metrics = compute_metrics(scored_cases)
            if quality_gate(metrics)["passed"]:
                viable.append((coverage, minimum_score, minimum_margin, metrics))
    if not viable:
        raise ScoringError("no ranking policy passes frozen quality thresholds")
    viable.sort(key=lambda item: (-item[0], item[1], item[2]))
    _, minimum_score, minimum_margin, metrics = viable[0]
    return {
        "selectedThresholds": {
            "minimumScore": minimum_score,
            "minimumMargin": minimum_margin,
        },
        "maximumCandidates": MAXIMUM_CANDIDATES,
        "calibrationCaseIdsSha256": _split_hash(calibration_ids),
        "testCaseIdsSha256": _split_hash(test_ids),
        "calibrationMetrics": metrics,
    }


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScoringError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise ScoringError(f"{path} root must be an object")
    return value


def _write_or_print(value: dict[str, Any], output: Path | None) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


def _score_command(dataset_path: Path, run_path: Path) -> dict[str, Any]:
    manifest = _load(dataset_path)
    validate_dataset_manifest(manifest)
    run = _load(run_path)
    metadata = {case["caseId"]: case for case in manifest["cases"]}
    case_results = run.get("caseResults")
    if not isinstance(case_results, list):
        raise ScoringError("run.caseResults must be an array")
    expected_test_ids = {
        case_id for case_id, case in metadata.items() if case["split"] == "test"
    }
    actual_ids = [result.get("caseId") for result in case_results]
    if len(actual_ids) != len(set(actual_ids)):
        raise ScoringError("run.caseResults contains duplicate caseId values")
    if set(actual_ids) != expected_test_ids:
        raise ScoringError("run must contain every frozen test split case exactly once")
    enriched = []
    for result in case_results:
        case_id = result.get("caseId")
        if case_id not in metadata:
            raise ScoringError(f"run contains unknown caseId: {case_id}")
        expected = metadata[case_id]
        if result.get("expectedFoodIdentities") != expected["expectedFoodIdentities"]:
            raise ScoringError(f"run changed frozen expected identities for {case_id}")
        enriched.append(
            {
                **result,
                "nonFood": expected["nonFood"],
                "stratum": expected["stratum"],
            }
        )
    metrics = compute_metrics(enriched)
    return {"metrics": metrics, "qualityGate": quality_gate(metrics)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    score = subparsers.add_parser("score")
    score.add_argument("--dataset", type=Path, required=True)
    score.add_argument("--run", type=Path, required=True)
    score.add_argument("--output", type=Path)
    calibrate = subparsers.add_parser("calibrate")
    calibrate.add_argument("--dataset", type=Path, required=True)
    calibrate.add_argument("--candidates", type=Path, required=True)
    calibrate.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "score":
        value = _score_command(arguments.dataset, arguments.run)
    else:
        manifest = _load(arguments.dataset)
        candidate_document = _load(arguments.candidates)
        rows = candidate_document.get("caseResults")
        if not isinstance(rows, list):
            raise ScoringError("candidates.caseResults must be an array")
        value = calibrate_thresholds(manifest, rows)
    _write_or_print(value, arguments.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScoringError as error:
        raise SystemExit(f"local food vision scoring failed: {error}") from error
