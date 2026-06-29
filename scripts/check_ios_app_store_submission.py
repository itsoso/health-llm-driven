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
    "NSSiriUsageDescription",
    "NSPhotoLibraryUsageDescription",
    "NSCameraUsageDescription",
    "NSMicrophoneUsageDescription",
    "NSSpeechRecognitionUsageDescription",
    "NSLocationWhenInUseUsageDescription",
    "NSHealthShareUsageDescription",
]

REQUIRED_EXTENSION_BUNDLE_IDS = {
    "life.executor.health.watchkitapp",
    "life.executor.health.watchkitapp.watchkitextension",
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

    for key in REQUIRED_INFO_PLIST_KEYS:
        value = info_plist.get(key)
        if not isinstance(value, str) or len(value.strip()) < 8:
            failures.append(f"missing or weak iOS usage string: {key}")

    names = plugin_names(app.get("plugins", []))
    for plugin in {"expo-router", "expo-secure-store", "react-native-health", "./plugins/withWatchApp"}:
        if plugin not in names:
            failures.append(f"missing required mobile plugin: {plugin}")

    project_id = app.get("extra", {}).get("eas", {}).get("projectId")
    updates_url = app.get("updates", {}).get("url")
    if not isinstance(project_id, str) or not project_id:
        failures.append("missing Expo EAS projectId")
    if project_id and updates_url != f"https://u.expo.dev/{project_id}":
        failures.append(f"updates.url must match EAS project id, got {updates_url!r}")

    extensions = app.get("extra", {}).get("eas", {}).get("build", {}).get("experimental", {}).get("ios", {}).get(
        "appExtensions",
        [],
    )
    extension_bundle_ids = {
        item.get("bundleIdentifier")
        for item in extensions
        if isinstance(item, dict) and isinstance(item.get("bundleIdentifier"), str)
    }
    missing_extensions = REQUIRED_EXTENSION_BUNDLE_IDS - extension_bundle_ids
    for missing in sorted(missing_extensions):
        failures.append(f"missing EAS app extension bundle id: {missing}")

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

    submit_ios = eas.get("submit", {}).get("production", {}).get("ios", {})
    asc_app_id = submit_ios.get("ascAppId")
    privacy_asc_app_id = privacy.get("app_store_connect_app_id")
    if asc_app_id != privacy_asc_app_id:
        failures.append(f"ASC app id mismatch: eas={asc_app_id!r}, privacy={privacy_asc_app_id!r}")
    if not isinstance(asc_app_id, str) or not asc_app_id.isdigit():
        failures.append(f"ASC app id must be a numeric string, got {asc_app_id!r}")

    submit_groups = submit_ios.get("groups")
    if not isinstance(submit_groups, list) or not submit_groups:
        failures.append("EAS submit production must name at least one TestFlight group")

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
        f"bundle_id={bundle_id} "
        f"asc_app_id={asc_app_id} "
        f"profile=production "
        f"project_id={project_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
