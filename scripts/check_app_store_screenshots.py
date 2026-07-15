#!/usr/bin/env python3
"""Validate App Store screenshot capture output.

The checker is intentionally metadata-driven: a screenshot set is not
submission-ready unless the capture manifest explicitly marks it as demo or
sanitized. This prevents real account screenshots from being promoted by
accident.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

REQUIRED_SCREENS = [
    "00-launch",
    "01-today",
    "02-chat",
    "03-record",
    "04-me",
    "05-import",
    "06-privacy",
]

APP_STORE_69_PORTRAIT_SIZES = {
    (1260, 2736),
    (1290, 2796),
    (1320, 2868),
}


def read_png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)

    if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG file")
    if header[12:16] != b"IHDR":
        raise ValueError("missing PNG IHDR")
    return struct.unpack(">II", header[16:24])


def load_manifest(directory: Path) -> dict[str, Any]:
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("missing manifest.json")

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json is invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("manifest.json must contain an object")
    return payload


def validate(
    directory: Path,
    *,
    app_store_ready: bool,
    expected_build_id: str | None = None,
) -> list[str]:
    failures: list[str] = []

    if not directory.exists() or not directory.is_dir():
        return [f"screenshot directory does not exist: {directory}"]

    try:
        manifest = load_manifest(directory)
    except ValueError as exc:
        return [str(exc)]

    privacy_status = manifest.get("privacy_status")
    if privacy_status not in {"private", "demo", "sanitized"}:
        failures.append("privacy_status must be one of: private, demo, sanitized")

    if app_store_ready:
        if privacy_status not in {"demo", "sanitized"}:
            failures.append("privacy_status must be demo or sanitized for App Store ready screenshots")
        if manifest.get("app_store_ready") is not True:
            failures.append("manifest app_store_ready must be true for App Store ready screenshots")

    if expected_build_id is not None:
        expected = str(expected_build_id).strip()
        actual_value = manifest.get("build_id")
        actual = str(actual_value).strip() if actual_value is not None else ""
        if actual != expected:
            rendered_actual = repr(actual) if actual else "missing"
            failures.append(
                "manifest build_id must match expected build: "
                f"expected {expected!r}, got {rendered_actual}"
            )

    screens = manifest.get("screens")
    if not isinstance(screens, list):
        failures.append("manifest screens must be a list")
        screens = []

    screen_by_name: dict[str, dict[str, Any]] = {}
    for item in screens:
        if not isinstance(item, dict):
            failures.append("manifest screens entries must be objects")
            continue
        name = item.get("name")
        if isinstance(name, str):
            screen_by_name[name] = item

    for name in REQUIRED_SCREENS:
        item = screen_by_name.get(name)
        if not item:
            failures.append(f"missing required screen in manifest: {name}")
            continue

        rel_file = item.get("file")
        if not isinstance(rel_file, str) or not rel_file.endswith(".png"):
            failures.append(f"{name} must point to a PNG file")
            continue

        image_path = directory / rel_file
        if not image_path.exists():
            failures.append(f"missing screenshot file: {rel_file}")
            continue

        try:
            width, height = read_png_size(image_path)
        except ValueError as exc:
            failures.append(f"{rel_file}: {exc}")
            continue

        if width >= height:
            failures.append(f"{rel_file} must be portrait, got {width}x{height}")
        if app_store_ready and (width, height) not in APP_STORE_69_PORTRAIT_SIZES:
            failures.append(f"{rel_file} has unsupported App Store size {width}x{height}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshot_dir", type=Path)
    parser.add_argument(
        "--app-store-ready",
        action="store_true",
        help="Require demo/sanitized manifest status and Apple 6.9-inch accepted dimensions.",
    )
    parser.add_argument(
        "--build-id",
        help="Require manifest build_id to match this App Store/TestFlight build number.",
    )
    args = parser.parse_args()

    failures = validate(
        args.screenshot_dir,
        app_store_ready=args.app_store_ready,
        expected_build_id=args.build_id,
    )
    if failures:
        print("App Store screenshot check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    manifest = load_manifest(args.screenshot_dir)
    print(
        "App Store screenshot check passed. "
        f"screens={len(REQUIRED_SCREENS)} "
        f"privacy_status={manifest.get('privacy_status')} "
        f"app_store_ready={bool(manifest.get('app_store_ready'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
