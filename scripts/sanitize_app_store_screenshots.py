#!/usr/bin/env python3
"""Create a review-required sanitized screenshot candidate from private QA captures.

This is not a substitute for a real demo account. It masks predictable private
regions and marks the output as requiring human visual review before
App Store-ready export.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

from check_app_store_screenshots import load_manifest, read_png_size, validate

MASKS_BY_SCREEN: dict[str, list[tuple[float, float, float, float, str]]] = {
    "*": [
        (0.00, 0.00, 1.00, 0.10, "status/header identity band"),
    ],
    "01-today": [
        (0.00, 0.10, 1.00, 0.24, "greeting and health summary band"),
        (0.05, 0.24, 0.95, 0.43, "top action health detail card"),
    ],
    "02-chat": [
        (0.04, 0.12, 0.96, 0.34, "recent chat context"),
    ],
    "04-me": [
        (0.00, 0.10, 1.00, 0.24, "account identity block"),
    ],
    "05-import": [
        (0.04, 0.18, 0.96, 0.42, "report list or upload context"),
    ],
}


def resolve_child(base: Path, rel_path: str) -> Path:
    resolved_base = base.resolve()
    resolved_child = (base / rel_path).resolve()
    if resolved_child != resolved_base and resolved_base not in resolved_child.parents:
        raise ValueError(f"screenshot path escapes directory: {rel_path}")
    return resolved_child


def ensure_output_dir(output_dir: Path, source_dir: Path, *, overwrite: bool) -> None:
    if output_dir.resolve() == source_dir.resolve():
        raise ValueError("output directory must be different from source directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise ValueError("output directory already exists and is not empty; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def screen_masks(screen_name: str) -> list[tuple[float, float, float, float, str]]:
    return [*MASKS_BY_SCREEN["*"], *MASKS_BY_SCREEN.get(screen_name, [])]


def apply_masks(source: Path, output: Path, *, screen_name: str) -> list[dict[str, Any]]:
    with Image.open(source) as image:
        working = image.convert("RGBA")
        width, height = working.size
        applied: list[dict[str, Any]] = []
        for left, top, right, bottom, reason in screen_masks(screen_name):
            box = (
                round(left * width),
                round(top * height),
                round(right * width),
                round(bottom * height),
            )
            region = working.crop(box).filter(ImageFilter.GaussianBlur(radius=24))
            working.paste(region, box)
            applied.append(
                {
                    "screen": screen_name,
                    "box": {"left": left, "top": top, "right": right, "bottom": bottom},
                    "reason": reason,
                }
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        working.convert(image.mode if image.mode in {"RGB", "RGBA"} else "RGB").save(output)
    return applied


def sanitize(source_dir: Path, output_dir: Path, *, overwrite: bool) -> None:
    failures = validate(source_dir, app_store_ready=False)
    if failures:
        joined = "\n".join(f"- {failure}" for failure in failures)
        raise ValueError(f"source screenshot set failed validation:\n{joined}")

    manifest = load_manifest(source_dir)
    if manifest.get("privacy_status") != "private":
        raise ValueError("source privacy_status must be private")

    ensure_output_dir(output_dir, source_dir, overwrite=overwrite)

    screens = manifest.get("screens")
    if not isinstance(screens, list):
        raise ValueError("manifest screens must be a list")

    all_masks: list[dict[str, Any]] = []
    output_screens: list[dict[str, Any]] = []
    for item in screens:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        rel_file = item.get("file")
        if not isinstance(name, str) or not isinstance(rel_file, str) or not rel_file.endswith(".png"):
            continue

        source_file = resolve_child(source_dir, rel_file)
        output_file = resolve_child(output_dir, rel_file)
        all_masks.extend(apply_masks(source_file, output_file, screen_name=name))
        if read_png_size(output_file) != read_png_size(source_file):
            raise RuntimeError(f"sanitized image size changed unexpectedly: {rel_file}")
        output_screens.append(dict(item))

    sanitized_manifest = dict(manifest)
    sanitized_manifest.update(
        {
            "sanitized_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "sanitized_by": "scripts/sanitize_app_store_screenshots.py",
            "sanitized_from": str(source_dir.resolve()),
            "privacy_status": "sanitized",
            "app_store_ready": False,
            "sanitization_review_required": True,
            "sanitization_method": "blur_relative_regions",
            "sanitization_masks": all_masks,
            "screens": output_screens,
        }
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(sanitized_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ready_failures = validate(output_dir, app_store_ready=False)
    if ready_failures:
        joined = "\n".join(f"- {failure}" for failure in ready_failures)
        raise RuntimeError(f"sanitized screenshot set failed validation:\n{joined}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing non-empty output directory.",
    )
    args = parser.parse_args()

    try:
        sanitize(args.source_dir, args.output_dir, overwrite=args.overwrite)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Sanitized App Store screenshot candidate written to {args.output_dir}")
    print("Human visual review is required before prepare_app_store_screenshots.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
