import json
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest


REQUIRED_NAMES = [
    "00-launch",
    "01-today",
    "02-chat",
    "03-record",
    "04-me",
    "05-import",
    "06-privacy",
]


def _write_png(path: Path, *, width: int = 1290, height: int = 2796) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanline = b"\x00" + b"\xff\xff\xff" * width
    raw = scanline * height
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, level=9))
        + chunk(b"IEND", b"")
    )


def _read_png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    return struct.unpack(">II", header[16:24])


def _write_manifest(
    directory: Path,
    *,
    privacy_status: str = "demo",
    app_store_ready: bool | None = None,
    width: int = 1290,
    height: int = 2796,
) -> None:
    screens = []
    for name in REQUIRED_NAMES:
        _write_png(directory / f"{name}.png", width=width, height=height)
        screens.append({"name": name, "file": f"{name}.png", "route": "/"})

    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-28T16:30:00Z",
                "privacy_status": privacy_status,
                "app_store_ready": (
                    privacy_status in {"demo", "sanitized"}
                    if app_store_ready is None
                    else app_store_ready
                ),
                "screens": screens,
            }
        ),
        encoding="utf-8",
    )


def _run_checker(root: Path, screenshot_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/check_app_store_screenshots.py",
            str(screenshot_dir),
            *extra,
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _run_prepare(
    root: Path,
    source_dir: Path,
    output_dir: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/prepare_app_store_screenshots.py",
            str(source_dir),
            str(output_dir),
            *extra,
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _run_sanitize(
    root: Path,
    source_dir: Path,
    output_dir: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/sanitize_app_store_screenshots.py",
            str(source_dir),
            str(output_dir),
            *extra,
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_app_store_screenshot_checker_accepts_demo_ready_set(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    screenshot_dir = tmp_path / "screens"
    screenshot_dir.mkdir()
    _write_manifest(screenshot_dir, privacy_status="demo")

    result = _run_checker(root, screenshot_dir, "--app-store-ready")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "App Store screenshot check passed." in result.stdout


def test_app_store_screenshot_checker_rejects_private_ready_set(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    screenshot_dir = tmp_path / "screens"
    screenshot_dir.mkdir()
    _write_manifest(screenshot_dir, privacy_status="private")

    result = _run_checker(root, screenshot_dir, "--app-store-ready")

    assert result.returncode == 1
    assert "privacy_status must be demo or sanitized" in result.stderr


def test_app_store_screenshot_checker_rejects_wrong_store_size(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    screenshot_dir = tmp_path / "screens"
    screenshot_dir.mkdir()
    _write_manifest(screenshot_dir, privacy_status="sanitized")
    _write_png(screenshot_dir / "02-chat.png", width=1206, height=2622)

    result = _run_checker(root, screenshot_dir, "--app-store-ready")

    assert result.returncode == 1
    assert "02-chat.png has unsupported App Store size 1206x2622" in result.stderr


def test_prepare_app_store_screenshots_creates_ready_sized_demo_set(tmp_path: Path):
    if shutil.which("sips") is None:
        pytest.skip("prepare_app_store_screenshots uses macOS sips for deterministic local release exports")

    root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "ready"
    source_dir.mkdir()
    _write_manifest(
        source_dir,
        privacy_status="demo",
        app_store_ready=False,
        width=1206,
        height=2622,
    )

    result = _run_prepare(root, source_dir, output_dir, "--size", "1290x2796")

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["privacy_status"] == "demo"
    assert manifest["app_store_ready"] is True
    assert manifest["target_size"] == {"width": 1290, "height": 2796}
    for name in REQUIRED_NAMES:
        assert _read_png_size(output_dir / f"{name}.png") == (1290, 2796)

    checker = _run_checker(root, output_dir, "--app-store-ready")
    assert checker.returncode == 0, checker.stdout + checker.stderr


def test_prepare_app_store_screenshots_refuses_private_source(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "ready"
    source_dir.mkdir()
    _write_manifest(source_dir, privacy_status="private", app_store_ready=False)

    result = _run_prepare(root, source_dir, output_dir)

    assert result.returncode == 1
    assert "source privacy_status must be demo or sanitized" in result.stderr


def test_prepare_app_store_screenshots_rejects_unsupported_target_size(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "ready"
    source_dir.mkdir()
    _write_manifest(source_dir, privacy_status="sanitized", app_store_ready=False)

    result = _run_prepare(root, source_dir, output_dir, "--size", "1206x2622")

    assert result.returncode == 1
    assert "target size must be one of" in result.stderr


def test_sanitize_app_store_screenshots_creates_review_required_candidate(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "private"
    output_dir = tmp_path / "sanitized"
    source_dir.mkdir()
    _write_manifest(source_dir, privacy_status="private", app_store_ready=False, width=1206, height=2622)

    result = _run_sanitize(root, source_dir, output_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["privacy_status"] == "sanitized"
    assert manifest["app_store_ready"] is False
    assert manifest["sanitization_review_required"] is True
    assert manifest["sanitized_from"].endswith("private")
    assert len(manifest["sanitization_masks"]) >= len(REQUIRED_NAMES)
    for name in REQUIRED_NAMES:
        assert _read_png_size(output_dir / f"{name}.png") == (1206, 2622)

    checker = _run_checker(root, output_dir)
    assert checker.returncode == 0, checker.stdout + checker.stderr


def test_sanitize_app_store_screenshots_masks_launch_and_chat_health_regions(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "private"
    output_dir = tmp_path / "sanitized"
    source_dir.mkdir()
    _write_manifest(source_dir, privacy_status="private", app_store_ready=False, width=1206, height=2622)

    result = _run_sanitize(root, source_dir, output_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    masks_by_screen: dict[str, list[str]] = {}
    for mask in manifest["sanitization_masks"]:
        masks_by_screen.setdefault(mask["screen"], []).append(mask["reason"])

    assert "launch mirrors Today health detail card" in masks_by_screen["00-launch"]
    assert "chat health suggestions and action list" in masks_by_screen["02-chat"]


def test_prepare_app_store_screenshots_requires_review_for_sanitized_candidate(tmp_path: Path):
    if shutil.which("sips") is None:
        pytest.skip("prepare_app_store_screenshots uses macOS sips for deterministic local release exports")

    root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "private"
    sanitized_dir = tmp_path / "sanitized"
    ready_dir = tmp_path / "ready"
    source_dir.mkdir()
    _write_manifest(source_dir, privacy_status="private", app_store_ready=False, width=1206, height=2622)
    sanitize = _run_sanitize(root, source_dir, sanitized_dir)
    assert sanitize.returncode == 0, sanitize.stdout + sanitize.stderr

    blocked = _run_prepare(root, sanitized_dir, ready_dir)

    assert blocked.returncode == 1
    assert "sanitized screenshots require human review" in blocked.stderr

    confirmed = _run_prepare(root, sanitized_dir, ready_dir, "--confirm-sanitized-reviewed")
    assert confirmed.returncode == 0, confirmed.stdout + confirmed.stderr
    checker = _run_checker(root, ready_dir, "--app-store-ready")
    assert checker.returncode == 0, checker.stdout + checker.stderr


def test_sanitize_app_store_screenshots_refuses_non_private_source(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    source_dir = tmp_path / "demo"
    output_dir = tmp_path / "sanitized"
    source_dir.mkdir()
    _write_manifest(source_dir, privacy_status="demo", app_store_ready=False)

    result = _run_sanitize(root, source_dir, output_dir)

    assert result.returncode == 1
    assert "source privacy_status must be private" in result.stderr
