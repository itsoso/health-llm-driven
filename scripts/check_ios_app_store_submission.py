#!/usr/bin/env python3
"""Validate iOS App Store build and submit configuration without uploading."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MOBILE_DIR = ROOT / "mobile"
RELEASE_DIR = ROOT / "docs/release/app-store"

REQUIRED_INFO_PLIST_KEYS = [
    "NSFaceIDUsageDescription",
    "NSPhotoLibraryUsageDescription",
    "NSCameraUsageDescription",
    "NSMicrophoneUsageDescription",
    "NSSpeechRecognitionUsageDescription",
    "NSLocationWhenInUseUsageDescription",
    "NSHealthShareUsageDescription",
]

FORBIDDEN_PRODUCTION_PLUGINS = {
    "./plugins/withWatchApp",
    "./plugins/withRokidIosPods",
    "./plugins/withRokidIosAuthCallback",
    "./plugins/withRokidPushupApk",
    "./plugins/withIntentsExtension",
}

EXPECTED_APP_NAME = "小巴"

REQUIRED_PRIVACY_DATA_TYPES = {
    "NSPrivacyCollectedDataTypeHealth",
    "NSPrivacyCollectedDataTypeFitness",
    "NSPrivacyCollectedDataTypeEmailAddress",
    "NSPrivacyCollectedDataTypeUserID",
    "NSPrivacyCollectedDataTypeOtherUserContent",
    "NSPrivacyCollectedDataTypePhotosorVideos",
    "NSPrivacyCollectedDataTypePreciseLocation",
    "NSPrivacyCollectedDataTypeCrashData",
    "NSPrivacyCollectedDataTypePerformanceData",
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def plugin_names(plugins: list[Any]) -> set[str]:
    names: set[str] = set()
    for plugin in plugins:
        if isinstance(plugin, str):
            names.add(plugin)
        elif isinstance(plugin, list) and plugin and isinstance(plugin[0], str):
            names.add(plugin[0])
    return names


def private_key_present(key_id: str | None) -> bool:
    if os.environ.get("ASC_PRIVATE_KEY_BASE64"):
        return True
    explicit = os.environ.get("ASC_PRIVATE_KEY_PATH")
    if explicit and Path(explicit).expanduser().exists():
        return True
    if key_id:
        default = Path.home() / ".appstoreconnect" / "private_keys" / f"AuthKey_{key_id}.p8"
        return default.exists()
    return False


def validate(require_asc_credentials: bool) -> list[str]:
    failures: list[str] = []

    try:
        app = read_json(MOBILE_DIR / "app.json")["expo"]
        eas = read_json(MOBILE_DIR / "eas.json")
        privacy = read_json(RELEASE_DIR / "privacy-nutrition-label.draft.json")
    except (KeyError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"cannot read App Store submission config: {exc}"]

    ios = app.get("ios", {})
    info_plist = ios.get("infoPlist", {})
    entitlements = ios.get("entitlements", {})
    bundle_id = ios.get("bundleIdentifier")
    privacy_bundle_id = privacy.get("bundle_id")
    if app.get("name") != EXPECTED_APP_NAME:
        failures.append(f"Expo app name must be {EXPECTED_APP_NAME!r}, got {app.get('name')!r}")
    if info_plist.get("CFBundleDisplayName") != EXPECTED_APP_NAME:
        failures.append(
            f"CFBundleDisplayName must be {EXPECTED_APP_NAME!r}, got {info_plist.get('CFBundleDisplayName')!r}"
        )
    if bundle_id != privacy_bundle_id:
        failures.append(f"bundle id mismatch: app.json={bundle_id!r}, privacy={privacy_bundle_id!r}")
    if bundle_id != "life.executor.health":
        failures.append(f"unexpected iOS bundle id: {bundle_id!r}")

    if entitlements.get("com.apple.developer.healthkit") is not True:
        failures.append("missing iOS HealthKit entitlement")
    if entitlements.get("aps-environment") != "production":
        failures.append("iOS aps-environment must be production for App Store submission")
    if info_plist.get("ITSAppUsesNonExemptEncryption") is not False:
        failures.append("ITSAppUsesNonExemptEncryption must be false or explicitly reviewed before submission")

    privacy_manifest = ios.get("privacyManifests", {})
    if privacy_manifest.get("NSPrivacyTracking") is not False:
        failures.append("iOS privacy manifest must explicitly disable tracking")
    if privacy_manifest.get("NSPrivacyTrackingDomains") != []:
        failures.append("iOS privacy manifest must not declare tracking domains")
    collected_entries = privacy_manifest.get("NSPrivacyCollectedDataTypes", [])
    collected_types = {
        entry.get("NSPrivacyCollectedDataType")
        for entry in collected_entries
        if isinstance(entry, dict)
    }
    missing_privacy_types = REQUIRED_PRIVACY_DATA_TYPES - collected_types
    if missing_privacy_types:
        failures.append(
            "iOS privacy manifest is missing collected data types: "
            + ", ".join(sorted(missing_privacy_types))
        )
    for entry in collected_entries:
        if isinstance(entry, dict) and entry.get("NSPrivacyCollectedDataTypeTracking") is not False:
            failures.append(
                "collected data type must explicitly disable tracking: "
                f"{entry.get('NSPrivacyCollectedDataType')!r}"
            )

    privacy_categories = {
        entry.get("category")
        for entry in privacy.get("data_types", [])
        if isinstance(entry, dict)
    }
    if not {"Health", "Fitness", "User Content", "Contact Info", "Identifiers", "Diagnostics", "Location"} <= privacy_categories:
        failures.append("App Store privacy label is missing one or more collected data categories")
    location_entry = next(
        (
            entry
            for entry in privacy.get("data_types", [])
            if isinstance(entry, dict) and entry.get("category") == "Location"
        ),
        {},
    )
    if not any("precise_location" in str(example) for example in location_entry.get("examples", [])):
        failures.append("App Store privacy label must declare precise location collection")
    if ios.get("supportsTablet") is not False:
        failures.append("App Store production must be iPhone-only until iPad acceptance is complete")
    if info_plist.get("UISupportedInterfaceOrientations") != ["UIInterfaceOrientationPortrait"]:
        failures.append("App Store production must support portrait orientation only")
    if "UISupportedInterfaceOrientations~ipad" in info_plist:
        failures.append("App Store production must not declare iPad orientations")
    if info_plist.get("UIBackgroundModes"):
        failures.append("App Store production must not declare unverified background modes")
    for key in (
        "NSLocationAlwaysUsageDescription",
        "NSLocationAlwaysAndWhenInUseUsageDescription",
        "NSBluetoothAlwaysUsageDescription",
        "NSBluetoothPeripheralUsageDescription",
        "NSSiriUsageDescription",
        "RokidCXRAuthCallbackScheme",
    ):
        if key in info_plist:
            failures.append(f"App Store production must not declare deferred capability: {key}")

    for key in REQUIRED_INFO_PLIST_KEYS:
        value = info_plist.get(key)
        if not isinstance(value, str) or len(value.strip()) < 8:
            failures.append(f"missing or weak iOS usage string: {key}")

    names = plugin_names(app.get("plugins", []))
    for plugin in {"expo-router", "expo-secure-store", "react-native-health"}:
        if plugin not in names:
            failures.append(f"missing required mobile plugin: {plugin}")
    for plugin in sorted(FORBIDDEN_PRODUCTION_PLUGINS & names):
        failures.append(f"deferred plugin must not be in App Store production: {plugin}")
    build_properties = next(
        (
            plugin[1]
            for plugin in app.get("plugins", [])
            if isinstance(plugin, list)
            and len(plugin) > 1
            and plugin[0] == "expo-build-properties"
            and isinstance(plugin[1], dict)
        ),
        {},
    )
    if build_properties.get("ios", {}).get("privacyManifestAggregationEnabled") is not True:
        failures.append("Expo privacy manifest aggregation must be enabled for iOS dependencies")

    project_id = app.get("extra", {}).get("eas", {}).get("projectId")
    updates_url = app.get("updates", {}).get("url")
    if not isinstance(project_id, str) or not project_id:
        failures.append("missing Expo EAS projectId")
    if project_id and updates_url != f"https://u.expo.dev/{project_id}":
        failures.append(f"updates.url must match EAS project id, got {updates_url!r}")

    extensions = app.get("extra", {}).get("eas", {}).get("build", {}).get("experimental", {}).get("ios", {}).get(
        "appExtensions", [],
    )
    if extensions:
        failures.append("App Store production must not include Watch app extensions")

    production = eas.get("build", {}).get("production", {})
    production_ios = production.get("ios", {})
    production_env = production.get("env", {})
    if production.get("channel") != "production":
        failures.append("EAS production build channel must be production")
    if production.get("distribution") == "internal":
        failures.append("EAS production build must not use internal distribution")
    if production_ios.get("autoIncrement") is not True:
        failures.append("EAS production iOS autoIncrement must be true")
    if production_env.get("APP_VARIANT") != "production":
        failures.append("EAS production env APP_VARIANT must be production")
    if production_env.get("SENTRY_DISABLE_AUTO_UPLOAD") != "true":
        failures.append("EAS production env must keep SENTRY_DISABLE_AUTO_UPLOAD=true unless release owner enables upload")
    for key in ("ROKID_IOS_SDK_ENABLED", "INCLUDE_WATCH_APP", "INCLUDE_SIRI_INTENTS"):
        if production_env.get(key) == "1":
            failures.append(f"EAS production must not enable deferred capability: {key}")

    submit_ios = eas.get("submit", {}).get("production", {}).get("ios", {})
    asc_app_id = submit_ios.get("ascAppId")
    privacy_asc_app_id = privacy.get("app_store_connect_app_id")
    if asc_app_id != privacy_asc_app_id:
        failures.append(f"ASC app id mismatch: eas={asc_app_id!r}, privacy={privacy_asc_app_id!r}")
    if not isinstance(asc_app_id, str) or not asc_app_id.isdigit():
        failures.append(f"ASC app id must be a numeric string, got {asc_app_id!r}")

    submit_groups = submit_ios.get("groups")
    if submit_groups:
        failures.append(
            "EAS submit production must not set TestFlight groups; "
            "Apple currently rejects internal group assignment after upload"
        )

    run_mobile_tf = ROOT / "scripts/_run-mobile-tf.sh"
    if not run_mobile_tf.exists():
        failures.append("missing scripts/_run-mobile-tf.sh submission helper")
    else:
        script_text = run_mobile_tf.read_text(encoding="utf-8")
        if "--profile production" not in script_text or "--auto-submit" not in script_text:
            failures.append("scripts/_run-mobile-tf.sh must use production profile with --auto-submit")

    if require_asc_credentials:
        key_id = os.environ.get("ASC_KEY_ID") or os.environ.get("APP_STORE_CONNECT_API_KEY")
        issuer_id = os.environ.get("ASC_ISSUER_ID") or os.environ.get("APP_STORE_CONNECT_ISSUER_ID")
        missing_credentials: list[str] = []
        if not key_id:
            missing_credentials.append("ASC_KEY_ID or APP_STORE_CONNECT_API_KEY")
        if not issuer_id:
            missing_credentials.append("ASC_ISSUER_ID or APP_STORE_CONNECT_ISSUER_ID")
        if not private_key_present(key_id):
            missing_credentials.append(
                "ASC_PRIVATE_KEY_PATH, ASC_PRIVATE_KEY_BASE64, or ~/.appstoreconnect/private_keys/AuthKey_<key>.p8"
            )
        if missing_credentials:
            failures.append("missing App Store Connect credentials: " + "; ".join(missing_credentials))

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-asc-credentials",
        action="store_true",
        help="Also require local App Store Connect API credentials for upload/submit commands.",
    )
    args = parser.parse_args()

    failures = validate(require_asc_credentials=args.require_asc_credentials)
    if failures:
        print("iOS App Store submission preflight failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    app = read_json(MOBILE_DIR / "app.json")["expo"]
    eas = read_json(MOBILE_DIR / "eas.json")
    bundle_id = app["ios"]["bundleIdentifier"]
    asc_app_id = eas["submit"]["production"]["ios"]["ascAppId"]
    project_id = app["extra"]["eas"]["projectId"]
    print(
        "iOS App Store submission preflight passed. "
        f"app_name={app['name']} "
        f"bundle_id={bundle_id} "
        f"asc_app_id={asc_app_id} "
        f"profile=production "
        f"project_id={project_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
