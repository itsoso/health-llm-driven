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


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ScoringError(f"cannot hash {path}: {error}") from error


def _write_or_print(value: dict[str, Any], output: Path | None) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


def _score_run(manifest: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
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


def _score_command(dataset_path: Path, run_path: Path) -> dict[str, Any]:
    manifest = _load(dataset_path)
    validate_dataset_manifest(manifest)
    return _score_run(manifest, _load(run_path))


def _variant_profile(
    run: dict[str, Any],
    *,
    precision: str,
    variant: dict[str, Any],
    manifest: dict[str, Any],
    label_bank: dict[str, Any],
    calibration_sha256: str,
    thresholds: dict[str, Any],
) -> int:
    dataset = run.get("dataset")
    profile = run.get("modelProfile")
    if not isinstance(dataset, dict) or dataset.get("version") != manifest["datasetVersion"]:
        raise ScoringError("raw run dataset version does not match the frozen manifest")
    if not isinstance(profile, dict) or profile.get("engine") != "custom_core_ml":
        raise ScoringError("raw run must use custom_core_ml")
    if profile.get("precisionVariant") != precision:
        raise ScoringError(f"raw run precision must equal {precision}")
    if profile.get("version") != variant["modelRevision"]:
        raise ScoringError("raw run model revision does not match variant evidence")
    if profile.get("labelBankVersion") != label_bank["labelSetVersion"]:
        raise ScoringError("raw run label version does not match variant evidence")
    if profile.get("calibrationVersion") != "cn-clip-calibration-v2":
        raise ScoringError("raw run calibration version does not match variant evidence")
    if profile.get("calibrationManifestSha256") != calibration_sha256:
        raise ScoringError("raw run calibration manifest hash does not match variant evidence")
    expected_policy = {
        "minimumScore": thresholds["minimumScore"],
        "minimumMargin": thresholds["minimumMargin"],
        "maximumCandidates": MAXIMUM_CANDIDATES,
    }
    actual_policy = {key: profile.get(key) for key in expected_policy}
    if actual_policy != expected_policy:
        raise ScoringError("raw run ranking policy does not match release calibration")

    artifact_hashes = {
        value for key in ("packageSha256", "compiledSha256")
        if isinstance((value := variant["artifact"].get(key)), str)
    }
    if profile.get("modelArtifactSha256") not in artifact_hashes:
        raise ScoringError("raw run model artifact hash does not match variant evidence")
    if profile.get("installedModelBytes") != variant["artifact"].get("compiledBytes"):
        raise ScoringError("raw run installed model bytes do not match variant evidence")
    if profile.get("installedLabelBankBytes") != label_bank["bytes"]:
        raise ScoringError("raw run installed label bytes do not match variant evidence")
    installed = profile["installedModelBytes"] + profile["installedLabelBankBytes"]
    if installed != variant["artifact"].get("totalInstalledBytes"):
        raise ScoringError("raw run installed assets do not match variant evidence")
    return installed


def _validate_release_calibration(
    calibration: dict[str, Any],
    manifest: dict[str, Any],
    *,
    model_revision: str,
    label_set_version: str,
) -> str:
    if calibration.get("status") != "pass":
        raise ScoringError("calibration manifest must have pass status")
    version = calibration.get("calibrationVersion")
    if version != "cn-clip-calibration-v2":
        raise ScoringError("calibration version must equal cn-clip-calibration-v2")
    if calibration.get("modelRevision") != model_revision:
        raise ScoringError("calibration model revision does not match variants")
    if calibration.get("labelSetVersion") != label_set_version:
        raise ScoringError("calibration label version does not match variants")

    thresholds = calibration.get("selectedThresholds")
    floor = calibration.get("rankingPolicyFloor")
    if not isinstance(thresholds, dict) or not isinstance(floor, dict):
        raise ScoringError("calibration thresholds are missing")
    score = thresholds.get("minimumScore")
    margin = thresholds.get("minimumMargin")
    if not isinstance(score, (int, float)) or not math.isfinite(float(score)) or score < MINIMUM_SCORE_FLOOR:
        raise ScoringError("calibration minimum score is below the frozen floor")
    if not isinstance(margin, (int, float)) or not math.isfinite(float(margin)) or margin < MINIMUM_MARGIN_FLOOR:
        raise ScoringError("calibration minimum margin is below the frozen floor")
    if floor != {
        "minimumScore": MINIMUM_SCORE_FLOOR,
        "minimumMargin": MINIMUM_MARGIN_FLOOR,
        "maximumCandidates": MAXIMUM_CANDIDATES,
    }:
        raise ScoringError("calibration ranking floor has drifted")

    calibration_ids = [
        case["caseId"] for case in manifest["cases"] if case["split"] == "calibration"
    ]
    test_ids = [case["caseId"] for case in manifest["cases"] if case["split"] == "test"]
    expected_splits = {
        "calibrationSplit": {
            "caseCount": len(calibration_ids),
            "caseIdsSha256": _split_hash(calibration_ids),
        },
        "testSplit": {
            "caseCount": len(test_ids),
            "caseIdsSha256": _split_hash(test_ids),
        },
    }
    for field, expected in expected_splits.items():
        if calibration.get(field) != expected:
            raise ScoringError(f"calibration {field} does not match the frozen dataset")
    return version


def _compare_command(
    dataset_path: Path,
    fp16_run_path: Path,
    compressed_run_path: Path,
    variants_path: Path,
    calibration_path: Path,
) -> dict[str, Any]:
    manifest = _load(dataset_path)
    validate_dataset_manifest(manifest)
    fp16_run = _load(fp16_run_path)
    compressed_run = _load(compressed_run_path)
    variants = _load(variants_path)
    calibration = _load(calibration_path)

    try:
        model_revision = variants["modelRevision"]
        label_bank = variants["labelBank"]
        budget = variants["packageBudgetBytes"]
        fp16_artifact = variants["variants"]["fp16"]
        compressed_artifact = variants["variants"]["int8"]
    except (KeyError, TypeError) as error:
        raise ScoringError("variants manifest is incomplete") from error
    if not isinstance(model_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", model_revision):
        raise ScoringError("variants manifest model revision is invalid")
    if not isinstance(label_bank, dict) or label_bank.get("labelSetVersion") != "cn-food-labels-v2":
        raise ScoringError("variants manifest label version is invalid")
    if not isinstance(label_bank.get("bytes"), int) or label_bank["bytes"] <= 0:
        raise ScoringError("variants manifest label bytes are invalid")
    if not isinstance(budget, int) or budget <= 0:
        raise ScoringError("variants manifest asset budget is invalid")
    calibration_version = _validate_release_calibration(
        calibration,
        manifest,
        model_revision=model_revision,
        label_set_version=label_bank["labelSetVersion"],
    )
    calibration_sha256 = _sha256(calibration_path)
    thresholds = calibration["selectedThresholds"]

    fp16_variant = {"modelRevision": model_revision, "artifact": fp16_artifact}
    compressed_variant = {"modelRevision": model_revision, "artifact": compressed_artifact}
    fp16_bytes = _variant_profile(
        fp16_run,
        precision="fp16",
        variant=fp16_variant,
        manifest=manifest,
        label_bank=label_bank,
        calibration_sha256=calibration_sha256,
        thresholds=thresholds,
    )
    compressed_bytes = _variant_profile(
        compressed_run,
        precision="int8-linear-per-channel-65536",
        variant=compressed_variant,
        manifest=manifest,
        label_bank=label_bank,
        calibration_sha256=calibration_sha256,
        thresholds=thresholds,
    )
    fp16_score = _score_run(manifest, fp16_run)
    compressed_score = _score_run(manifest, compressed_run)
    comparison = compare_variants(
        fp16_score["metrics"],
        compressed_score["metrics"],
        fp16_asset_bytes=fp16_bytes,
        compressed_asset_bytes=compressed_bytes,
    )
    selected = {
        "fp16": "fp16",
        "compressed": "int8-linear-per-channel-65536",
        None: None,
    }[comparison["selectedVariant"]]
    test_ids = [
        case["caseId"] for case in manifest["cases"] if case["split"] == "test"
    ]
    return {
        "schemaVersion": 1,
        "datasetVersion": manifest["datasetVersion"],
        "datasetManifestSha256": _sha256(dataset_path),
        "testCaseIdsSha256": _split_hash(test_ids),
        "modelRevision": model_revision,
        "labelSetVersion": label_bank["labelSetVersion"],
        "calibrationVersion": calibration_version,
        "calibrationManifestSha256": calibration_sha256,
        "variantsManifestSha256": _sha256(variants_path),
        "fp16": {
            "runSha256": _sha256(fp16_run_path),
            "precisionVariant": "fp16",
            "installedAssetBytes": fp16_bytes,
            "foodIdentityPrecision": fp16_score["metrics"]["foodIdentityPrecision"],
            "qualityGate": fp16_score["qualityGate"],
        },
        "compressed": {
            "runSha256": _sha256(compressed_run_path),
            "precisionVariant": "int8-linear-per-channel-65536",
            "installedAssetBytes": compressed_bytes,
            "foodIdentityPrecision": compressed_score["metrics"]["foodIdentityPrecision"],
            "qualityGate": compressed_score["qualityGate"],
        },
        "absoluteIdentityPrecisionDelta": comparison["absoluteIdentityPrecisionDelta"],
        "assetBudgetBytes": budget,
        "selectedVariant": selected,
        "verdict": comparison["verdict"],
    }


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
    compare = subparsers.add_parser("compare")
    compare.add_argument("--dataset", type=Path, required=True)
    compare.add_argument("--fp16-run", type=Path, required=True)
    compare.add_argument("--compressed-run", type=Path, required=True)
    compare.add_argument("--variants-manifest", type=Path, required=True)
    compare.add_argument("--calibration-manifest", type=Path, required=True)
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "score":
        value = _score_command(arguments.dataset, arguments.run)
    elif arguments.command == "calibrate":
        manifest = _load(arguments.dataset)
        candidate_document = _load(arguments.candidates)
        rows = candidate_document.get("caseResults")
        if not isinstance(rows, list):
            raise ScoringError("candidates.caseResults must be an array")
        value = calibrate_thresholds(manifest, rows)
    else:
        value = _compare_command(
            arguments.dataset,
            arguments.fp16_run,
            arguments.compressed_run,
            arguments.variants_manifest,
            arguments.calibration_manifest,
        )
    _write_or_print(value, arguments.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScoringError as error:
        raise SystemExit(f"local food vision scoring failed: {error}") from error
