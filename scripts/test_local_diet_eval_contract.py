#!/usr/bin/env python3
"""Regression tests for the local-diet on-device evidence contract."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs/evals/local-diet/on-device-eval-contract.json"
VARIANT_SCHEMA_PATH = ROOT / "docs/evals/local-diet/chinese-clip-variant-evidence-contract.json"
SYSTEM_MODEL_RUNS = sorted(
    (ROOT / "docs/evals/local-diet/runs").glob("*-system-model.json")
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def base_report(engine: str = "custom_core_ml", precision: str = "fp16") -> dict:
    model_profile = {
        "engine": engine,
        "identifier": "OFA-Sys/chinese-clip-rn50-image-tower",
        "version": "717ba215769231e53b9b7c6b9d329b9cc5944418",
        "downloadBytes": 39_626_225,
    }
    summary = {
        "caseCount": 1,
        "crashFreeCompletionRate": 1,
        "validTypedDraftRate": 1,
        "foodIdentityPrecision": 1,
        "missingItemRate": 0,
        "nonFoodRejectionRate": 1,
        "medianCorrectionCount": 0,
        "p90CorrectionCount": 0,
        "textP95WarmLatencyMs": None,
        "visionP95WarmLatencyMs": 120,
        "maxPeakMemoryDeltaMb": 48,
        "worstThermalState": "nominal",
        "gateVerdict": "blocked",
    }
    if engine == "custom_core_ml":
        model_profile.update(
            {
                "modelArtifactSha256": "a" * 64,
                "labelBankVersion": "cn-food-labels-v2",
                "calibrationVersion": "cn-clip-calibration-v2",
                "calibrationManifestSha256": "c" * 64,
                "minimumScore": 0.5,
                "minimumMargin": 0.03,
                "maximumCandidates": 3,
                "installedModelBytes": 39_296_441,
                "installedLabelBankBytes": 329_784,
                "precisionVariant": precision,
            }
        )
        summary["oneSecondCompletionRate"] = 1

    return {
        "contractVersion": "1.0.0",
        "runId": "opaque-run-001",
        "recordedAt": "2026-07-18T20:00:00Z",
        "dataset": {
            "name": "authorized-food-eval",
            "version": "v1",
            "licenseStatus": "licensed_for_evaluation",
            "containsPrivateUserData": False,
        },
        "device": {
            "hardwareIdentifier": "iPhone18,2",
            "deviceClass": "phone",
            "osVersion": "iOS 26.6",
            "isSimulator": False,
            "appBuild": "g2-spike",
        },
        "capabilities": {
            "schemaVersion": 1,
            "osVersion": "iOS 26.6",
            "deviceClass": "phone",
            "isSimulator": False,
            "systemLanguageModel": {
                "available": False,
                "reason": "device_not_eligible",
            },
            "multimodalLanguageModel": {
                "available": False,
                "reason": "sdk_not_supported",
            },
            "vision": {
                "textRecognition": True,
                "imageClassification": True,
                "barcodeDetection": True,
            },
        },
        "modelProfile": model_profile,
        "caseResults": [
            {
                "caseId": "opaque-case-001",
                "inputModality": "photo",
                "fixtureRef": "fixture-001",
                "expectedFoodIdentities": ["rice"],
                "allowedAliases": {},
                "quantityAmbiguity": "unknown",
                "nonFood": False,
                "predictedFoodIdentities": ["rice"],
                "validTypedDraft": True,
                "correctionCount": 0,
                "coldLatencyMs": 250,
                "warmLatencyMs": 120,
                "peakMemoryDeltaMb": 48,
                "thermalStateBefore": "nominal",
                "thermalStateAfter": "nominal",
                "crashed": False,
            }
        ],
        "summary": summary,
    }


class LocalDietEvalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_json(SCHEMA_PATH)
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def assert_valid(self, report: dict) -> None:
        errors = sorted(self.validator.iter_errors(report), key=lambda error: list(error.path))
        self.assertEqual([], [error.message for error in errors])

    def assert_invalid(self, report: dict) -> None:
        self.assertTrue(list(self.validator.iter_errors(report)))

    def test_custom_core_ml_fp16_evidence_is_valid(self) -> None:
        self.assert_valid(base_report())

    def test_custom_core_ml_requires_artifact_and_asset_provenance(self) -> None:
        fields = [
            "modelArtifactSha256",
            "labelBankVersion",
            "calibrationVersion",
            "calibrationManifestSha256",
            "minimumScore",
            "minimumMargin",
            "maximumCandidates",
            "installedModelBytes",
            "installedLabelBankBytes",
            "precisionVariant",
        ]
        for field in fields:
            with self.subTest(field=field):
                report = base_report()
                del report["modelProfile"][field]
                self.assert_invalid(report)

    def test_custom_core_ml_requires_one_second_completion_rate(self) -> None:
        report = base_report()
        del report["summary"]["oneSecondCompletionRate"]
        self.assert_invalid(report)

    def test_raw_compressed_run_does_not_claim_a_comparison_delta(self) -> None:
        report = base_report(precision="int8-linear-per-channel-65536")
        self.assert_valid(report)
        report["summary"]["fp16ToCompressedIdentityPrecisionDelta"] = 0.01
        self.assert_invalid(report)

    def test_raw_fp16_run_does_not_claim_a_comparison_delta(self) -> None:
        report = base_report()
        report["summary"]["fp16ToCompressedIdentityPrecisionDelta"] = 0
        self.assert_invalid(report)

    def test_legacy_system_model_contract_remains_valid_without_custom_fields(self) -> None:
        self.assert_valid(base_report(engine="apple_foundation_models"))

    def test_private_dataset_and_device_identifiers_are_rejected(self) -> None:
        private = base_report()
        private["dataset"]["containsPrivateUserData"] = True
        self.assert_invalid(private)

        for identifier in [
            "00008120-001C2D1234567890",
            "F2LZQ0ABC123",
        ]:
            with self.subTest(identifier=identifier):
                report = base_report()
                report["device"]["hardwareIdentifier"] = identifier
                self.assert_invalid(report)

    def test_committed_system_model_evidence_has_no_private_data_or_raw_identifier(self) -> None:
        self.assertTrue(SYSTEM_MODEL_RUNS)
        for path in SYSTEM_MODEL_RUNS:
            with self.subTest(path=path.name):
                run = load_json(path)
                self.assertFalse(run["containsPrivateUserData"])
                identifier = run["report"]["device"]["hardwareIdentifier"]
                self.assertEqual("iPhone18,2", identifier)
                self.assertNotRegex(json.dumps(run), r"[0-9A-Fa-f]{8}-[0-9A-Fa-f-]{20,}")


class ChineseClipVariantEvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_json(VARIANT_SCHEMA_PATH)
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_derived_variant_evidence_requires_input_hashes_and_measured_delta(self) -> None:
        evidence = {
            "schemaVersion": 1,
            "datasetVersion": "authorized-v1",
            "datasetManifestSha256": "a" * 64,
            "testCaseIdsSha256": "b" * 64,
            "modelRevision": "7" * 40,
            "labelSetVersion": "cn-food-labels-v2",
            "calibrationVersion": "cn-clip-calibration-v2",
            "calibrationManifestSha256": "f" * 64,
            "variantsManifestSha256": "c" * 64,
            "fp16": {
                "runSha256": "d" * 64,
                "precisionVariant": "fp16",
                "installedAssetBytes": 77_074_808,
                "foodIdentityPrecision": 0.9,
                "qualityGate": {"passed": True, "failures": []},
            },
            "compressed": {
                "runSha256": "e" * 64,
                "precisionVariant": "int8-linear-per-channel-65536",
                "installedAssetBytes": 39_660_136,
                "foodIdentityPrecision": 0.89,
                "qualityGate": {"passed": True, "failures": []},
            },
            "absoluteIdentityPrecisionDelta": 0.01,
            "assetBudgetBytes": 52_428_800,
            "selectedVariant": "int8-linear-per-channel-65536",
            "verdict": "pass",
        }
        self.assertEqual([], list(self.validator.iter_errors(evidence)))

        for field in [
            "datasetManifestSha256",
            "calibrationManifestSha256",
            "fp16",
            "compressed",
        ]:
            invalid = deepcopy(evidence)
            del invalid[field]
            self.assertTrue(list(self.validator.iter_errors(invalid)))


if __name__ == "__main__":
    unittest.main()
