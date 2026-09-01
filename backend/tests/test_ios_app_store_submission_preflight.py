import os
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path


def _run_preflight(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/check_ios_app_store_submission.py", *extra],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_ios_app_store_submission_preflight_passes_repo_config():
    root = Path(__file__).resolve().parents[2]

    result = _run_preflight(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "iOS App Store submission preflight passed." in result.stdout
    assert "app_name=小巴健康" in result.stdout
    assert "bundle_id=life.executor.health" in result.stdout
    assert "asc_app_id=6763569720" in result.stdout

    app = json.loads((root / "mobile/app.json").read_text(encoding="utf-8"))["expo"]
    plugin_names = {
        plugin[0] if isinstance(plugin, list) else plugin
        for plugin in app["plugins"]
    }
    assert app["ios"]["supportsTablet"] is False
    assert app["ios"]["infoPlist"]["UISupportedInterfaceOrientations"] == [
        "UIInterfaceOrientationPortrait"
    ]
    assert "UIBackgroundModes" not in app["ios"]["infoPlist"]
    assert "./plugins/withWatchApp" not in plugin_names
    assert "./plugins/withRokidIosPods" not in plugin_names
    assert "./plugins/withIntentsExtension" not in plugin_names
    privacy_manifest = app["ios"]["privacyManifests"]
    assert privacy_manifest["NSPrivacyTracking"] is False
    collected_types = {
        item["NSPrivacyCollectedDataType"]
        for item in privacy_manifest["NSPrivacyCollectedDataTypes"]
    }
    assert {
        "NSPrivacyCollectedDataTypeHealth",
        "NSPrivacyCollectedDataTypeFitness",
        "NSPrivacyCollectedDataTypeEmailAddress",
        "NSPrivacyCollectedDataTypeUserID",
        "NSPrivacyCollectedDataTypeOtherUserContent",
        "NSPrivacyCollectedDataTypePhotosorVideos",
        "NSPrivacyCollectedDataTypeAudioData",
        "NSPrivacyCollectedDataTypePreciseLocation",
        "NSPrivacyCollectedDataTypeDeviceID",
        "NSPrivacyCollectedDataTypeProductInteraction",
        "NSPrivacyCollectedDataTypeCrashData",
        "NSPrivacyCollectedDataTypePerformanceData",
    } <= collected_types


def test_ios_app_store_submission_preflight_requires_all_published_privacy_types():
    from scripts.check_ios_app_store_submission import REQUIRED_PRIVACY_DATA_TYPES

    assert {
        "NSPrivacyCollectedDataTypeAudioData",
        "NSPrivacyCollectedDataTypeDeviceID",
        "NSPrivacyCollectedDataTypeProductInteraction",
    } <= REQUIRED_PRIVACY_DATA_TYPES


def test_ios_privacy_manifest_alignment_fails_closed_for_semantic_mutations():
    from scripts.check_ios_app_store_submission import validate_privacy_manifest_against_label

    root = Path(__file__).resolve().parents[2]
    app = json.loads((root / "mobile/app.json").read_text(encoding="utf-8"))["expo"]
    label = json.loads(
        (root / "docs/release/app-store/privacy-nutrition-label.draft.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = app["ios"]["privacyManifests"]

    assert validate_privacy_manifest_against_label(manifest, label) == []

    def manifest_entry(payload: dict, data_type: str) -> dict:
        return next(
            item
            for item in payload["NSPrivacyCollectedDataTypes"]
            if item["NSPrivacyCollectedDataType"] == data_type
        )

    mutations: list[dict] = []

    missing = deepcopy(manifest)
    missing["NSPrivacyCollectedDataTypes"] = missing["NSPrivacyCollectedDataTypes"][1:]
    mutations.append(missing)

    extra = deepcopy(manifest)
    extra["NSPrivacyCollectedDataTypes"].append(
        {
            "NSPrivacyCollectedDataType": "NSPrivacyCollectedDataTypePhoneNumber",
            "NSPrivacyCollectedDataTypeLinked": True,
            "NSPrivacyCollectedDataTypeTracking": False,
            "NSPrivacyCollectedDataTypePurposes": [
                "NSPrivacyCollectedDataTypePurposeAppFunctionality"
            ],
        }
    )
    mutations.append(extra)

    duplicate_type = deepcopy(manifest)
    duplicate_type["NSPrivacyCollectedDataTypes"].append(
        deepcopy(duplicate_type["NSPrivacyCollectedDataTypes"][0])
    )
    mutations.append(duplicate_type)

    linked_flip = deepcopy(manifest)
    manifest_entry(linked_flip, "NSPrivacyCollectedDataTypeAudioData")[
        "NSPrivacyCollectedDataTypeLinked"
    ] = False
    mutations.append(linked_flip)

    tracking_flip = deepcopy(manifest)
    manifest_entry(tracking_flip, "NSPrivacyCollectedDataTypeProductInteraction")[
        "NSPrivacyCollectedDataTypeTracking"
    ] = True
    mutations.append(tracking_flip)

    missing_purpose = deepcopy(manifest)
    manifest_entry(missing_purpose, "NSPrivacyCollectedDataTypeUserID")[
        "NSPrivacyCollectedDataTypePurposes"
    ] = ["NSPrivacyCollectedDataTypePurposeAppFunctionality"]
    mutations.append(missing_purpose)

    extra_purpose = deepcopy(manifest)
    manifest_entry(extra_purpose, "NSPrivacyCollectedDataTypeUserID")[
        "NSPrivacyCollectedDataTypePurposes"
    ].append("NSPrivacyCollectedDataTypePurposeOther")
    mutations.append(extra_purpose)

    duplicate_purpose = deepcopy(manifest)
    manifest_entry(duplicate_purpose, "NSPrivacyCollectedDataTypeProductInteraction")[
        "NSPrivacyCollectedDataTypePurposes"
    ].append("NSPrivacyCollectedDataTypePurposeAnalytics")
    mutations.append(duplicate_purpose)

    root_tracking_flip = deepcopy(manifest)
    root_tracking_flip["NSPrivacyTracking"] = True
    mutations.append(root_tracking_flip)

    for mutated in mutations:
        assert validate_privacy_manifest_against_label(mutated, label)

    double_deleted_manifest = deepcopy(manifest)
    double_deleted_manifest["NSPrivacyCollectedDataTypes"] = [
        item
        for item in double_deleted_manifest["NSPrivacyCollectedDataTypes"]
        if item["NSPrivacyCollectedDataType"] != "NSPrivacyCollectedDataTypeAudioData"
    ]
    double_deleted_label = deepcopy(label)
    user_content = next(
        item for item in double_deleted_label["data_types"] if item["category"] == "User Content"
    )
    user_content["apple_data_types"].remove("Audio Data")
    del user_content["apple_data_type_details"]["Audio Data"]
    assert validate_privacy_manifest_against_label(double_deleted_manifest, double_deleted_label)

    tracking_manifest = deepcopy(manifest)
    tracking_manifest["NSPrivacyTracking"] = True
    tracking_label = deepcopy(label)
    tracking_label["tracking"] = True
    tracking_label["data_not_used_for_tracking"] = False
    assert validate_privacy_manifest_against_label(tracking_manifest, tracking_label)

    type_tracking_manifest = deepcopy(manifest)
    manifest_entry(type_tracking_manifest, "NSPrivacyCollectedDataTypeProductInteraction")[
        "NSPrivacyCollectedDataTypeTracking"
    ] = True
    type_tracking_label = deepcopy(label)
    next(
        item
        for item in type_tracking_label["data_types"]
        if item["category"] == "Usage Data"
    )["used_for_tracking"] = True
    assert validate_privacy_manifest_against_label(type_tracking_manifest, type_tracking_label)

    unknown_type_label = deepcopy(label)
    unknown_type_label["data_types"].append(
        {
            "category": "Unknown",
            "apple_data_types": ["Unknown Apple Type"],
            "purpose": ["app_functionality"],
            "linked_to_user": True,
            "used_for_tracking": False,
        }
    )
    assert validate_privacy_manifest_against_label(manifest, unknown_type_label)

    unknown_purpose_label = deepcopy(label)
    unknown_purpose_label["data_types"][0]["purpose"].append("unknown_purpose")
    assert validate_privacy_manifest_against_label(manifest, unknown_purpose_label)


def test_ios_app_store_submission_preflight_requires_asc_credentials_when_requested():
    root = Path(__file__).resolve().parents[2]
    scrubbed_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ASC_") and not key.startswith("APP_STORE_CONNECT_")
    }

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_ios_app_store_submission.py",
            "--require-asc-credentials",
        ],
        cwd=root,
        env=scrubbed_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert "missing App Store Connect credentials" in result.stderr
