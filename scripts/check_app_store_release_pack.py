#!/usr/bin/env python3
"""Validate App Store release materials against mobile config."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "docs/release/app-store/submission-pack.md",
    "docs/release/app-store/privacy-nutrition-label.draft.json",
    "docs/release/app-store/review-notes.zh-CN.md",
    "docs/release/app-store/screenshot-runbook.md",
    "docs/plans/2026-06-28-app-store-mvp-release-batch2-plan.md",
    "docs/plans/2026-06-28-app-store-mvp-release-batch3-plan.md",
    "docs/plans/2026-06-28-app-store-mvp-release-batch4-plan.md",
    "frontend/src/app/privacy/page.tsx",
    "scripts/sim-build.sh",
    "scripts/mobile-sim-screenshots.sh",
    "scripts/check_app_store_screenshots.py",
]

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

MEDICAL_BOUNDARY_TERMS = [
    "不提供诊断",
    "处方",
    "药物剂量调整",
]

OFFICIAL_REFERENCE_URLS = [
    "https://developer.apple.com/support/offering-account-deletion-in-your-app/",
    "https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications/",
    "https://developer.apple.com/help/app-store-connect/manage-app-privacy/app-privacy-details/",
    "https://developer.apple.com/app-store/review/guidelines/",
]


def read_json(path: str) -> dict:
    with (ROOT / path).open(encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            failures.append(f"missing required file: {rel}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    app = read_json("mobile/app.json")["expo"]
    ios = app.get("ios", {})
    info_plist = ios.get("infoPlist", {})
    entitlements = ios.get("entitlements", {})
    eas = read_json("mobile/eas.json")
    privacy = read_json("docs/release/app-store/privacy-nutrition-label.draft.json")
    submission = read_text("docs/release/app-store/submission-pack.md")
    review_notes = read_text("docs/release/app-store/review-notes.zh-CN.md")
    privacy_page = read_text("frontend/src/app/privacy/page.tsx")

    bundle_id = ios.get("bundleIdentifier")
    if bundle_id != privacy.get("bundle_id"):
        failures.append(f"bundle id mismatch: app.json={bundle_id!r}, privacy={privacy.get('bundle_id')!r}")

    if entitlements.get("com.apple.developer.healthkit") is not True:
        failures.append("missing iOS HealthKit entitlement")

    for key in REQUIRED_INFO_PLIST_KEYS:
        value = info_plist.get(key)
        if not isinstance(value, str) or len(value.strip()) < 8:
            failures.append(f"missing or weak iOS privacy usage string: {key}")

    asc_app_id = eas.get("submit", {}).get("production", {}).get("ios", {}).get("ascAppId")
    if asc_app_id != privacy.get("app_store_connect_app_id"):
        failures.append(
            f"ASC app id mismatch: eas={asc_app_id!r}, privacy={privacy.get('app_store_connect_app_id')!r}"
        )

    privacy_url = privacy.get("privacy_policy_url", "")
    if privacy_url != "https://health.executor.life/privacy":
        failures.append(f"unexpected privacy policy url: {privacy_url!r}")

    if privacy.get("tracking") is not False:
        failures.append("privacy label must declare tracking=false for this release")
    if privacy.get("healthkit_advertising_use") is not False:
        failures.append("HealthKit advertising use must remain false")

    categories = {item.get("category") for item in privacy.get("data_types", [])}
    for category in {"Health", "Fitness", "User Content", "Contact Info", "Identifiers", "Diagnostics"}:
        if category not in categories:
            failures.append(f"privacy nutrition missing category: {category}")

    combined_release_text = "\n".join([submission, review_notes, privacy_page])
    for term in MEDICAL_BOUNDARY_TERMS:
        if term not in combined_release_text:
            failures.append(f"medical boundary term missing from release text: {term}")

    for required in ["HealthKit", "删除账号与数据", "广告", "营销", "support@executor.life"]:
        if required not in combined_release_text:
            failures.append(f"release text missing required wording: {required}")

    for url in OFFICIAL_REFERENCE_URLS:
        if url not in submission and url not in read_text("docs/plans/2026-06-28-app-store-mvp-release-batch2-plan.md"):
            failures.append(f"missing official reference URL: {url}")

    if "[NEEDS APP STORE REVIEW DEMO ACCOUNT]" not in review_notes:
        failures.append("review notes must keep an explicit demo-account placeholder until owner provides credentials")

    screenshot_dir = os.environ.get("APP_STORE_SCREENSHOT_DIR")
    if screenshot_dir:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/check_app_store_screenshots.py"),
                screenshot_dir,
                "--app-store-ready",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            failures.append(
                "App Store screenshot set failed validation; "
                f"APP_STORE_SCREENSHOT_DIR={screenshot_dir!r}\n{result.stderr.strip()}"
            )

    if failures:
        print("App Store release pack check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("App Store release pack check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
