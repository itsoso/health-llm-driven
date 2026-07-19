#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "score_local_food_vision_run.py"
SPEC = importlib.util.spec_from_file_location("score_local_food_vision_run", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC) if SPEC else None
if SPEC and SPEC.loader and MODULE:
    SPEC.loader.exec_module(MODULE)


class ScoreLocalFoodVisionRunTests(unittest.TestCase):
    def test_dataset_contract_requires_300_authorized_non_private_stratified_cases(self) -> None:
        manifest = dataset_manifest(300)
        MODULE.validate_dataset_manifest(manifest)

        for mutation in [
            lambda value: value.update(containsPrivateUserData=True),
            lambda value: value["cases"].pop(),
            lambda value: value["cases"][0].update(licenseStatus="unknown"),
            lambda value: value["cases"][0].update(fixtureId="lunch-photo.jpg"),
            lambda value: value["cases"][0].update(sourcePath="/private/photo.jpg"),
        ]:
            invalid = json.loads(json.dumps(manifest))
            mutation(invalid)
            with self.assertRaises(MODULE.ScoringError):
                MODULE.validate_dataset_manifest(invalid)

    def test_precision_deduplicates_predictions_and_mixed_plate_omissions_count(self) -> None:
        metrics = MODULE.compute_metrics(
            [
                result_case(
                    expected=["rice"],
                    predicted=["rice", "rice", "screen"],
                    stratum="single_item",
                ),
                result_case(
                    expected=["rice", "fish", "broccoli"],
                    predicted=["rice", "fish"],
                    stratum="mixed_plate",
                ),
            ]
        )

        self.assertEqual(metrics["foodIdentityPrecision"], 0.75)
        self.assertEqual(metrics["missingItemRate"], 0.25)
        self.assertEqual(metrics["top1Accuracy"], 1)
        self.assertEqual(metrics["top3Accuracy"], 1)
        self.assertEqual(metrics["perStratum"]["mixed_plate"]["missingItemRate"], 1 / 3)

    def test_non_food_crash_latency_correction_and_one_second_metrics_are_exact(self) -> None:
        metrics = MODULE.compute_metrics(
            [
                result_case(
                    expected=[], predicted=[], non_food=True,
                    stratum="non_food_adversarial", warm=800,
                ),
                result_case(
                    expected=[], predicted=["rice"], non_food=True,
                    stratum="non_food_adversarial", warm=1_200,
                ),
                result_case(
                    expected=["rice"], predicted=[], crashed=True,
                    stratum="degraded_adversarial", warm=0,
                ),
            ]
        )

        self.assertEqual(metrics["nonFoodRejectionRate"], 0.5)
        self.assertEqual(metrics["crashFreeCompletionRate"], 2 / 3)
        self.assertEqual(metrics["oneSecondCompletionRate"], 1 / 3)
        self.assertEqual(metrics["p95WarmLatencyMs"], 1_200)
        self.assertEqual(metrics["medianCorrectionCount"], 1)
        self.assertEqual(metrics["p90CorrectionCount"], 1)

    def test_quality_gate_uses_frozen_release_thresholds(self) -> None:
        passing = {
            "crashFreeCompletionRate": 1,
            "validTypedDraftRate": 0.95,
            "foodIdentityPrecision": 0.85,
            "missingItemRate": 0.1,
            "nonFoodRejectionRate": 0.98,
            "medianCorrectionCount": 1,
            "p90CorrectionCount": 2,
        }
        self.assertTrue(MODULE.quality_gate(passing)["passed"])
        failing = dict(passing, foodIdentityPrecision=0.849999)
        verdict = MODULE.quality_gate(failing)
        self.assertFalse(verdict["passed"])
        self.assertIn("foodIdentityPrecision", verdict["failures"])

    def test_compressed_selection_requires_delta_quality_and_50mb_budget(self) -> None:
        fp16 = passing_metrics(precision=0.9)
        compressed = passing_metrics(precision=0.89)
        selected = MODULE.compare_variants(
            fp16,
            compressed,
            fp16_asset_bytes=77_040_897,
            compressed_asset_bytes=39_626_225,
        )
        self.assertEqual(selected["verdict"], "pass")
        self.assertEqual(selected["selectedVariant"], "compressed")
        self.assertAlmostEqual(selected["absoluteIdentityPrecisionDelta"], 0.01)

        too_different = MODULE.compare_variants(
            fp16,
            passing_metrics(precision=0.87),
            fp16_asset_bytes=77_040_897,
            compressed_asset_bytes=39_626_225,
        )
        self.assertEqual(too_different["verdict"], "blocked")
        self.assertIsNone(too_different["selectedVariant"])

    def test_calibration_uses_only_calibration_split_and_freezes_split_hashes(self) -> None:
        manifest = dataset_manifest(300)
        rows = candidate_rows(manifest, test_top_score=0.99)
        first = MODULE.calibrate_thresholds(manifest, rows)
        rows[-1]["candidates"][0]["score"] = 0.01
        second = MODULE.calibrate_thresholds(manifest, rows)

        self.assertEqual(first["selectedThresholds"], second["selectedThresholds"])
        self.assertEqual(first["calibrationCaseIdsSha256"], second["calibrationCaseIdsSha256"])
        self.assertEqual(first["testCaseIdsSha256"], second["testCaseIdsSha256"])
        self.assertGreaterEqual(first["selectedThresholds"]["minimumScore"], 0.5)
        self.assertGreaterEqual(first["selectedThresholds"]["minimumMargin"], 0.03)
        self.assertEqual(first["maximumCandidates"], 3)

    def test_cli_has_no_flags_that_can_lower_release_quality_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "dataset.json"
            run_path = Path(directory) / "run.json"
            manifest_path.write_text(json.dumps(small_calibration_manifest()), encoding="utf-8")
            run_path.write_text(json.dumps({"caseResults": []}), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    MODULE.main(
                        [
                            "score", "--dataset", str(manifest_path),
                            "--run", str(run_path), "--min-precision", "0",
                        ]
                    )

    def test_score_command_requires_complete_frozen_test_split(self) -> None:
        manifest = dataset_manifest(300)
        results = []
        for case in manifest["cases"]:
            if case["split"] != "test":
                continue
            results.append(
                {
                    "caseId": case["caseId"],
                    "expectedFoodIdentities": case["expectedFoodIdentities"],
                    "predictedFoodIdentities": case["expectedFoodIdentities"],
                    "nonFood": not case["nonFood"],
                    "crashed": False,
                    "validTypedDraft": True,
                    "warmLatencyMs": 100,
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "dataset.json"
            run_path = Path(directory) / "run.json"
            dataset_path.write_text(json.dumps(manifest), encoding="utf-8")
            run_path.write_text(json.dumps({"caseResults": results}), encoding="utf-8")

            scored = MODULE._score_command(dataset_path, run_path)
            self.assertTrue(scored["qualityGate"]["passed"])

            results.pop()
            run_path.write_text(json.dumps({"caseResults": results}), encoding="utf-8")
            with self.assertRaises(MODULE.ScoringError):
                MODULE._score_command(dataset_path, run_path)

    def test_committed_calibration_manifest_is_fail_closed_without_authorized_data(self) -> None:
        module_root = SCRIPT.parents[1]
        repository_root = module_root.parents[2]
        calibration_path = module_root / "model-manifests/chinese-clip-calibration-v1.json"
        calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
        dataset_contract = repository_root / calibration["datasetContract"]["path"]

        self.assertEqual(calibration["status"], "blocked_pending_authorized_dataset")
        self.assertIsNone(calibration["selectedThresholds"])
        self.assertIsNone(calibration["variantEvidence"]["selectedVariant"])
        self.assertEqual(calibration["rankingPolicyFloor"]["minimumScore"], MODULE.MINIMUM_SCORE_FLOOR)
        self.assertEqual(calibration["rankingPolicyFloor"]["minimumMargin"], MODULE.MINIMUM_MARGIN_FLOOR)
        self.assertEqual(calibration["rankingPolicyFloor"]["maximumCandidates"], MODULE.MAXIMUM_CANDIDATES)
        self.assertEqual(
            hashlib.sha256(dataset_contract.read_bytes()).hexdigest(),
            calibration["datasetContract"]["sha256"],
        )


def result_case(
    *, expected: list[str], predicted: list[str], stratum: str,
    non_food: bool = False, crashed: bool = False, warm: float = 500,
) -> dict:
    return {
        "caseId": f"case-{stratum}-{len(expected)}-{len(predicted)}-{warm}",
        "expectedFoodIdentities": expected,
        "predictedFoodIdentities": predicted,
        "nonFood": non_food,
        "stratum": stratum,
        "crashed": crashed,
        "validTypedDraft": not crashed,
        "warmLatencyMs": warm,
    }


def passing_metrics(precision: float) -> dict:
    return {
        "crashFreeCompletionRate": 1,
        "validTypedDraftRate": 1,
        "foodIdentityPrecision": precision,
        "missingItemRate": 0,
        "nonFoodRejectionRate": 1,
        "medianCorrectionCount": 0,
        "p90CorrectionCount": 0,
    }


STRATA = [
    "single_item",
    "composite_dish",
    "mixed_plate",
    "packaged_food_drink",
    "confusable_pair",
    "non_food_adversarial",
    "degraded_adversarial",
]


def dataset_manifest(count: int) -> dict:
    cases = []
    for index in range(count):
        stratum = STRATA[index % len(STRATA)]
        non_food = stratum == "non_food_adversarial"
        expected = [] if non_food else (["rice", "fish"] if stratum == "mixed_plate" else ["rice"])
        cases.append(
            {
                "caseId": f"case-{index:04d}",
                "fixtureId": f"fixture-{index:04d}",
                "split": "calibration" if index % 3 == 0 else "test",
                "stratum": stratum,
                "licenseStatus": "synthetic",
                "expectedFoodIdentities": expected,
                "nonFood": non_food,
            }
        )
    return {
        "schemaVersion": 1,
        "datasetVersion": "test-v1",
        "containsPrivateUserData": False,
        "cases": cases,
    }


def small_calibration_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "datasetVersion": "small-v1",
        "containsPrivateUserData": False,
        "cases": [
            {
                "caseId": "case-cal-food",
                "fixtureId": "fixture-cal-food",
                "split": "calibration",
                "stratum": "single_item",
                "licenseStatus": "synthetic",
                "expectedFoodIdentities": ["rice"],
                "nonFood": False,
            },
            {
                "caseId": "case-cal-non-food",
                "fixtureId": "fixture-cal-non-food",
                "split": "calibration",
                "stratum": "non_food_adversarial",
                "licenseStatus": "synthetic",
                "expectedFoodIdentities": [],
                "nonFood": True,
            },
            {
                "caseId": "case-test-food",
                "fixtureId": "fixture-test-food",
                "split": "test",
                "stratum": "single_item",
                "licenseStatus": "synthetic",
                "expectedFoodIdentities": ["fish"],
                "nonFood": False,
            },
        ],
    }


def candidate_rows(manifest: dict, test_top_score: float) -> list[dict]:
    rows = []
    for case in manifest["cases"]:
        if case["nonFood"]:
            candidates = [
                {"canonicalFoodId": "negative.screen", "score": 0.95, "kind": "non_food"}
            ]
        else:
            candidates = [
                {
                    "canonicalFoodId": food_id,
                    "score": 0.9 - index * 0.1,
                    "kind": "food",
                }
                for index, food_id in enumerate(case["expectedFoodIdentities"])
            ]
        rows.append({"caseId": case["caseId"], "candidates": candidates})
    rows[-1]["candidates"][0]["score"] = test_top_score
    return rows


if __name__ == "__main__":
    unittest.main()
