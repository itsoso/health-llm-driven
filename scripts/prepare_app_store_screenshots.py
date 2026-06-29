#!/usr/bin/env python3
"""Prepare a demo or sanitized screenshot set for App Store upload.

This script is intentionally fail-closed: private screenshots are never
promoted into an App Store-ready set. Operators must first capture with a demo
account or a sanitized data build, then this script exports the images to an
accepted 6.9-inch portrait size and writes a ready manifest.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from check_app_store_screenshots import (
    APP_STORE_69_PORTRAIT_SIZES,
    load_manifest,
    read_png_size,
    validate,
)

DEFAULT_TARGET_SIZE = (1290, 2796)


def format_size(size: tuple[int, int]) -> str:
    width, height = size
    return f"{width}x{height}"


def accepted_sizes_text() -> str:
    return ", ".join(format_size(size) for size in sorted(APP_STORE_69_PORTRAIT_SIZES))


def parse_target_size(raw: str) -> tuple[int, int]:
    parts = raw.lower().split("x", maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"target size must be one of: {accepted_sizes_text()}")

    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"target size must be one of: {accepted_sizes_text()}") from exc

    size = (width, height)
    if size not in APP_STORE_69_PORTRAIT_SIZES:
        raise ValueError(f"target size must be one of: {accepted_sizes_text()}")
    return size


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


def run_sips_resize(source: Path, output: Path, *, target_size: tuple[int, int]) -> None:
    width, height = target_size
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "sips",
            "-z",
            str(height),
            str(width),
            str(source),
            "--out",
            str(output),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"sips failed for {source.name}: {detail}")

    actual_size = read_png_size(output)
    if actual_size != target_size:
        raise RuntimeError(
            f"sips wrote unexpected size for {output.name}: "
            f"{format_size(actual_size)} != {format_size(target_size)}"
        )


def prepare(
    source_dir: Path,
    output_dir: Path,
    *,
    target_size: tuple[int, int],
    privacy_status: str | None,
    overwrite: bool,
) -> None:
    failures = validate(source_dir, app_store_ready=False)
    if failures:
        joined = "\n".join(f"- {failure}" for failure in failures)
        raise ValueError(f"source screenshot set failed validation:\n{joined}")

    manifest = load_manifest(source_dir)
    source_privacy_status = manifest.get("privacy_status")
    if source_privacy_status not in {"demo", "sanitized"}:
        raise ValueError("source privacy_status must be demo or sanitized")

    output_privacy_status = privacy_status or source_privacy_status
    if output_privacy_status not in {"demo", "sanitized"}:
        raise ValueError("output privacy_status must be demo or sanitized")

    if shutil.which("sips") is None:
        raise RuntimeError("sips not found; run this export on macOS")

    ensure_output_dir(output_dir, source_dir, overwrite=overwrite)

    source_screens = manifest.get("screens")
    if not isinstance(source_screens, list):
        raise ValueError("manifest screens must be a list")

    output_screens: list[dict[str, Any]] = []
    for item in source_screens:
        if not isinstance(item, dict):
            continue
        rel_file = item.get("file")
        if not isinstance(rel_file, str) or not rel_file.endswith(".png"):
            continue

        source_file = resolve_child(source_dir, rel_file)
        output_file = resolve_child(output_dir, rel_file)
        run_sips_resize(source_file, output_file, target_size=target_size)
        output_screens.append(dict(item))

    width, height = target_size
    prepared_manifest = dict(manifest)
    prepared_manifest.update(
        {
            "prepared_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "prepared_by": "scripts/prepare_app_store_screenshots.py",
            "prepared_from": str(source_dir.resolve()),
            "privacy_status": output_privacy_status,
            "app_store_ready": True,
            "target_size": {"width": width, "height": height},
            "screens": output_screens,
        }
    )

    (output_dir / "manifest.json").write_text(
        json.dumps(prepared_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ready_failures = validate(output_dir, app_store_ready=True)
    if ready_failures:
        joined = "\n".join(f"- {failure}" for failure in ready_failures)
        raise RuntimeError(f"prepared screenshot set failed validation:\n{joined}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--size",
        default=format_size(DEFAULT_TARGET_SIZE),
        help=f"Target 6.9-inch portrait size. Accepted: {accepted_sizes_text()}.",
    )
    parser.add_argument(
        "--privacy-status",
        choices=["demo", "sanitized"],
        help="Override output manifest privacy status after human review.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing non-empty output directory.",
    )
    args = parser.parse_args()

    try:
        target_size = parse_target_size(args.size)
        prepare(
            args.source_dir,
            args.output_dir,
            target_size=target_size,
            privacy_status=args.privacy_status,
            overwrite=args.overwrite,
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        "Prepared App Store screenshots. "
        f"output={args.output_dir} "
        f"size={format_size(target_size)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
